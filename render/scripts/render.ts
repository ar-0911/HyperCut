// npm run render -- --plan plan.json --video source.mp4 --out out.mp4
//
// Bundles the Remotion project, serves the video from a throw-away public dir, and renders the plan.
// Env: REMOTION_BROWSER = path to a Chrome/Chromium binary (otherwise Remotion's own download, then
// any Playwright Chromium under PLAYWRIGHT_BROWSERS_PATH or /opt/pw-browsers).

import {bundle} from '@remotion/bundler';
import {renderMedia, selectComposition} from '@remotion/renderer';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {normalizePlan} from '../src/plan';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');

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

/** Find a Chromium binary: explicit env first, else a Playwright install. Undefined lets Remotion download one. */
export function findBrowser(env = process.env): string | undefined {
	if (env.REMOTION_BROWSER) return env.REMOTION_BROWSER;
	const base = env.PLAYWRIGHT_BROWSERS_PATH || '/opt/pw-browsers';
	if (!fs.existsSync(base)) return undefined;
	const candidates = ['chrome-linux/chrome', 'chrome-linux/headless_shell', 'chrome-linux64/chrome'];
	const dirs = fs.readdirSync(base).filter((d) => /^chromium/.test(d)).sort().reverse();
	for (const d of dirs) {
		for (const c of candidates) {
			const p = path.join(base, d, c);
			if (fs.existsSync(p)) return p;
		}
	}
	return undefined;
}

/** File names of the imported media a plan uses. Plain names only: nothing outside the asset folder. */
export function mediaFiles(plan: {graphics: {type: string; props: Record<string, unknown>}[]}): string[] {
	const names = new Set<string>();
	for (const g of plan.graphics) {
		if (g.type !== 'media') continue;
		const name = String(g.props.src ?? '');
		if (!name || name !== path.basename(name) || name.startsWith('.')) throw new Error(`bad media file name: ${JSON.stringify(name)}`);
		names.add(name);
	}
	return [...names];
}

async function main() {
	const args = parseArgs(process.argv.slice(2));
	if (!args.plan || !args.video || !args.out) {
		console.error('usage: npm run render -- --plan <plan.json> --video <file> --out <mp4> [--assets <dir>] [--composition HyperCut] [--concurrency N]');
		process.exit(2);
	}
	const planPath = path.resolve(args.plan);
	const videoPath = path.resolve(args.video);
	const outPath = path.resolve(args.out);
	if (!fs.existsSync(planPath)) throw new Error(`plan not found: ${planPath}`);
	if (!fs.existsSync(videoPath)) throw new Error(`video not found: ${videoPath}`);

	const plan = normalizePlan(JSON.parse(fs.readFileSync(planPath, 'utf8')));

	const publicDir = fs.mkdtempSync(path.join(os.tmpdir(), 'hypercut-public-'));
	const videoName = `source${path.extname(videoPath) || '.mp4'}`;
	// The bundler copies publicDir and drops symlinks, so link the real file (hard link is free, copy if
	// the video is on another filesystem).
	const place = (from: string, name: string) => {
		try {
			fs.linkSync(from, path.join(publicDir, name));
		} catch {
			fs.copyFileSync(from, path.join(publicDir, name));
		}
	};
	place(videoPath, videoName);
	// Imported media (B-roll) sits next to the video unless --assets says otherwise.
	const assetDir = path.resolve(args.assets ?? path.dirname(videoPath));
	for (const name of mediaFiles(plan)) {
		const from = path.join(assetDir, name);
		if (!fs.existsSync(from)) throw new Error(`imported file not found: ${from}`);
		if (!fs.existsSync(path.join(publicDir, name))) place(from, name);
	}

	try {
		const browserExecutable = findBrowser() ?? null;
		const serveUrl = await bundle({entryPoint: path.join(root, 'src/index.ts'), publicDir});
		const inputProps = {plan, videoSrc: videoName};
		const composition = await selectComposition({
			serveUrl,
			id: args.composition ?? 'HyperCut',
			inputProps,
			browserExecutable,
			chromiumOptions: {gl: 'swiftshader'},
		});
		fs.mkdirSync(path.dirname(outPath), {recursive: true});
		let last = -1;
		await renderMedia({
			composition,
			serveUrl,
			codec: 'h264',
			outputLocation: outPath,
			inputProps,
			browserExecutable,
			chromiumOptions: {gl: 'swiftshader'},
			concurrency: args.concurrency ? Number(args.concurrency) : null,
			onProgress: ({progress}) => {
				const pct = Math.floor(progress * 100);
				if (pct !== last && pct % 10 === 0) console.log(`render ${pct}%`);
				last = pct;
			},
		});
		console.log(`wrote ${outPath} (${composition.durationInFrames} frames, ${composition.width}x${composition.height} @ ${composition.fps}fps)`);
	} finally {
		fs.rmSync(publicDir, {recursive: true, force: true});
	}
}

main().catch((e) => {
	console.error(e instanceof Error ? e.message : e);
	process.exit(1);
});
