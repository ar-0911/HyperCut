// npm run render -- --plan plan.json --video source.mp4 --out out.mp4
//
// Renders a plan with HyperFrames (ADR 0032). The reel's frames are drawn by the same React components the
// editor previews; this script prepares a HyperFrames project for them and runs `hyperframes render`:
//
//   1. a dry run draws every frame once and lists the video frames and the sound the reel uses
//   2. ffmpeg extracts exactly those frames (so every video frame is exact, never a seeked <video>)
//   3. index.html holds the plan, the sound as <audio> clips and the page script (dist/hypercut-page.js)
//   4. HyperFrames seeks the page frame by frame in headless Chrome, mixes the sound and encodes
//
// Env: HYPERCUT_BROWSER (or REMOTION_BROWSER, the old name) = a Chrome/Chromium binary; otherwise a Playwright
// install under PLAYWRIGHT_BROWSERS_PATH or /opt/pw-browsers. HyperFrames' anonymous usage reporting is off.

import {spawn, spawnSync} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import React from 'react';
import {audioClips, collect} from '../src/collect';
import {setStaticBase, type FrameDir} from '../src/frame';
import {compositionHtml, type PageConfig} from '../src/hf/html';
import {extractArgs, frameRuns} from '../src/hf/extract';
import {calculateMetadata, HyperCut} from '../src/HyperCut';
import {normalizePlan, type CompositionProps} from '../src/plan';

const here = path.dirname(fileURLToPath(import.meta.url));
// Run from source (tsx scripts/render.ts) or from the bundle (dist/render.mjs): the package root either way.
const root = fs.existsSync(path.join(here, 'package.json')) ? here : path.resolve(here, '..');

function parseArgs(argv: string[]): Record<string, string> {
	const out: Record<string, string> = {};
	for (let i = 0; i < argv.length; i++) {
		const a = argv[i];
		if (!a.startsWith('--')) continue;
		const [k, inline] = a.slice(2).split('=');
		out[k] = inline ?? argv[++i] ?? '';
	}
	return out;
}

/** Find a Chromium binary: explicit env first, else a Playwright install (the headless shell first). */
export function findBrowser(env = process.env): string | undefined {
	if (env.HYPERCUT_BROWSER) return env.HYPERCUT_BROWSER;
	if (env.REMOTION_BROWSER) return env.REMOTION_BROWSER;
	const base = env.PLAYWRIGHT_BROWSERS_PATH || '/opt/pw-browsers';
	if (!fs.existsSync(base)) return undefined;
	const candidates = [
		'chrome-headless-shell-linux64/chrome-headless-shell',
		'chrome-linux/headless_shell',
		'chrome-linux/chrome',
		'chrome-linux64/chrome',
	];
	const dirs = fs.readdirSync(base).filter((d) => /^chromium/.test(d)).sort((a, b) => Number(/headless/.test(b)) - Number(/headless/.test(a)) || b.localeCompare(a));
	for (const d of dirs) {
		for (const c of candidates) {
			const p = path.join(base, d, c);
			if (fs.existsSync(p)) return p;
		}
	}
	return undefined;
}

/** File names of the imported media a plan uses. Plain names only: nothing outside the asset folder. */
export function mediaFiles(plan: {
	graphics: {type: string; props: Record<string, unknown>}[];
	backgrounds?: {kind: string; src?: string | null}[];
	style?: {depth?: {enabled: boolean}};
	brand?: {logo?: string | null; music?: string | null; font?: string | null};
}): string[] {
	const names = new Set<string>();
	const add = (raw: unknown) => {
		const name = String(raw ?? '');
		if (!name || name !== path.basename(name) || name.startsWith('.')) throw new Error(`bad media file name: ${JSON.stringify(name)}`);
		names.add(name);
	};
	// Pictures and clips: imported, stock or generated (a request not fetched yet has no file and draws nothing).
	for (const g of plan.graphics) if ((g.type === 'media' || g.type === 'motion') && g.props.src) add(g.props.src);
	// Background pictures and clips behind the cut-out speaker (only drawn with green-screen effects on).
	if (plan.style?.depth?.enabled) for (const b of plan.backgrounds ?? []) if (b.kind === 'media' && b.src) add(b.src);
	// The brand kit's logo, music and font (ADR 0026).
	for (const f of [plan.brand?.logo, plan.brand?.music, plan.brand?.font]) if (f) add(f);
	return [...names];
}

/** The speaker cut-out made by `python -m hypercut.matte` (ADR 0901). */
export const MATTE_FILE = 'matte.webm';
/** Where media sits in the HyperFrames project (its convention: root-relative assets/). */
const ASSETS = 'assets/';

const place = (from: string, to: string) => {
	try {
		fs.linkSync(from, to);
	} catch {
		fs.copyFileSync(from, to);
	}
};

/** Seconds of a media file (for looping music), or undefined. */
function durationOf(file: string): number | undefined {
	const res = spawnSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file], {encoding: 'utf8'});
	const d = Number(res.stdout.trim());
	return Number.isFinite(d) && d > 0 ? d : undefined;
}

function run(cmd: string, args: string[], env?: NodeJS.ProcessEnv, onLine?: (line: string) => void): Promise<void> {
	return new Promise((resolve, reject) => {
		const p = spawn(cmd, args, {env, stdio: ['ignore', 'pipe', 'pipe']});
		let tail = '';
		const take = (b: Buffer) => {
			const s = b.toString();
			tail = (tail + s).slice(-4000);
			if (onLine) for (const line of s.split('\n')) if (line.trim()) onLine(line);
		};
		p.stdout.on('data', take);
		p.stderr.on('data', take);
		p.on('error', reject);
		p.on('close', (code) => (code === 0 ? resolve() : reject(new Error(`${path.basename(cmd)} failed (${code}): ${tail.trim()}`))));
	});
}

/** Run `jobs` with at most `n` at a time. */
async function pool(jobs: (() => Promise<void>)[], n: number) {
	let next = 0;
	await Promise.all(Array.from({length: Math.min(n, jobs.length)}, async () => {
		while (next < jobs.length) await jobs[next++]();
	}));
}

/** Extract the frames of `file` the reel draws into `dir`; any frame past the file's end repeats its last one. */
async function extractFrames(file: string, frames: Set<number>, fps: number, dir: string, alpha: boolean, cores: number) {
	fs.mkdirSync(dir, {recursive: true});
	const ext = alpha ? 'png' : 'jpg';
	await pool(frameRuns(frames).map((r) => () => run('ffmpeg', extractArgs(file, r, fps, dir, ext, alpha))), cores);
	const have = new Set(fs.readdirSync(dir));
	let held: string | null = null;
	for (const f of [...frames].sort((a, b) => a - b)) {
		const name = `${f}.${ext}`;
		if (have.has(name)) held = name;
		else if (held) place(path.join(dir, held), path.join(dir, name));
	}
}

async function main() {
	const args = parseArgs(process.argv.slice(2));
	if (!args.plan || !args.video || !args.out) {
		console.error('usage: npm run render -- --plan <plan.json> --video <file> --out <mp4> [--assets <dir>] [--matte <webm>] [--workers N] [--keep <dir>] [--overlays 1 (graphics only, ProRes 4444 .mov)]');
		process.exit(2);
	}
	const planPath = path.resolve(args.plan);
	const videoPath = path.resolve(args.video);
	const outPath = path.resolve(args.out);
	if (!fs.existsSync(planPath)) throw new Error(`plan not found: ${planPath}`);
	if (!fs.existsSync(videoPath)) throw new Error(`video not found: ${videoPath}`);
	const plan = normalizePlan(JSON.parse(fs.readFileSync(planPath, 'utf8')));

	const project = args.keep ? path.resolve(args.keep) : fs.mkdtempSync(path.join(os.tmpdir(), 'hypercut-hf-'));
	const assets = path.join(project, ASSETS);
	fs.mkdirSync(assets, {recursive: true});
	const videoName = `source${path.extname(videoPath) || '.mp4'}`;
	place(videoPath, path.join(assets, videoName));
	// Imported media (B-roll, brand kit) sits next to the video unless --assets says otherwise.
	const assetDir = path.resolve(args.assets ?? path.dirname(videoPath));
	for (const name of mediaFiles(plan)) {
		const from = path.join(assetDir, name);
		if (!fs.existsSync(from)) throw new Error(`imported file not found: ${from}`);
		if (!fs.existsSync(path.join(assets, name))) place(from, path.join(assets, name));
	}
	// A different background or things behind the speaker need the cut-out (ADR 0614); without it the reel
	// renders without those effects.
	const overlaysOnly = Boolean(args.overlays);
	let matteSrc: string | undefined;
	if (!overlaysOnly && plan.style.depth.enabled && plan.style.depth.cutout) {
		const matte = path.resolve(args.matte ?? path.join(path.dirname(videoPath), MATTE_FILE));
		if (fs.existsSync(matte)) {
			place(matte, path.join(assets, MATTE_FILE));
			matteSrc = MATTE_FILE;
		} else {
			console.warn(`no speaker cut-out at ${matte}; rendering without green-screen effects`);
		}
	}

	try {
		const props: CompositionProps = {plan, videoSrc: videoName, matteSrc, overlaysOnly};
		const meta = calculateMetadata({props});
		setStaticBase(ASSETS);
		const started = Date.now();
		const usage = collect(() => React.createElement(HyperCut, props), meta);
		const fileOf = (src: string) => path.join(project, decodeURIComponent(src));

		const cores = Math.max(1, os.cpus().length);
		const frames: Record<string, FrameDir> = {};
		let k = 0;
		for (const [src, use] of usage.pictures) {
			const dir = `frames/${k++}`;
			frames[src] = {dir, fps: meta.fps, ext: use.transparent ? 'png' : 'jpg'};
			await extractFrames(fileOf(src), use.frames, meta.fps, path.join(project, dir), use.transparent, cores);
		}
		const durations: Record<string, number> = {};
		for (const s of usage.sounds) if (s.loop && durations[s.src] === undefined) durations[s.src] = durationOf(fileOf(s.src)) ?? 0;
		const audio = audioClips(usage.sounds, meta.fps, durations);
		const pictures = [...usage.pictures.values()].reduce((n, p) => n + p.frames.size, 0);
		console.log(`prepared ${pictures} video frames and ${audio.length} sound clips in ${((Date.now() - started) / 1000).toFixed(1)}s`);

		const page = path.join(root, 'dist', 'hypercut-page.js');
		if (!fs.existsSync(page)) throw new Error(`page script missing: ${page} (run npm run build)`);
		fs.copyFileSync(page, path.join(project, 'hypercut-page.js'));
		const config: PageConfig = {mode: 'render', props, ...meta, staticBase: ASSETS, frames};
		fs.writeFileSync(path.join(project, 'index.html'), compositionHtml({config, audio, scripts: ['hypercut-page.js']}));

		fs.mkdirSync(path.dirname(outPath), {recursive: true});
		const bin = path.join(root, 'node_modules', '.bin', 'hyperframes');
		const browser = findBrowser();
		const env: NodeJS.ProcessEnv = {
			...process.env,
			HYPERFRAMES_NO_TELEMETRY: '1',
			DO_NOT_TRACK: '1',
			HYPERFRAMES_SKIP_SKILLS: '1',
			...(browser ? {HYPERFRAMES_BROWSER_PATH: browser} : {}),
		};
		// --overlays: the graphics and captions alone, on transparency, as ProRes 4444 (an editor export, ADR 0017).
		const format = overlaysOnly ? ['--format', 'mov'] : [];
		let last = -1;
		await run(
			bin,
			['render', project, '--output', outPath, '--fps', String(meta.fps), '--quality', 'high', ...format, ...(args.workers ? ['--workers', args.workers] : [])],
			env,
			(line) => {
				const m = /^@hf-progress (\{.*\})/.exec(line.trim());
				if (!m) return;
				const pct = Math.floor(Number(JSON.parse(m[1]).pct ?? 0) / 10) * 10;
				if (pct !== last) console.log(`render ${pct}%`);
				last = pct;
			},
		);
		if (!fs.existsSync(outPath)) throw new Error(`hyperframes wrote no ${outPath}`);
		console.log(`wrote ${outPath} (${meta.durationInFrames} frames, ${meta.width}x${meta.height} @ ${meta.fps}fps)`);
	} finally {
		if (!args.keep) fs.rmSync(project, {recursive: true, force: true});
	}
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain)
	main().catch((e) => {
		console.error(e instanceof Error ? e.message : e);
		process.exit(1);
	});
