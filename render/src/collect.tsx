// The dry run (ADR 0032): draw every frame of the reel once, without a page, to learn what it uses. The render
// script extracts exactly the video frames listed here, and the sound becomes HyperFrames <audio> clips, so the
// mix is the one the components ask for (cuts eased, J-cuts, music ducked under speech).

import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {FrameRoot, type MediaUse, type Runtime} from './frame';

/** One stretch of sound: `src` from `mediaStart` seconds, at output time `start` for `duration` seconds. */
export type AudioClip = {
	id: string;
	src: string;
	start: number;
	duration: number;
	mediaStart: number;
	rate: number;
	/** Gain over the clip (t: seconds from the clip's start, v: 1 = as recorded); one point when constant. */
	volume: {t: number; v: number}[];
};

export type Usage = {
	/** Per video file: the output-fps frame indices of it that are drawn, and whether it keeps its alpha. */
	pictures: Map<string, {frames: Set<number>; transparent: boolean}>;
	sounds: MediaUse[];
};

/** Draw frames 0..total-1 of `draw(frame)` and record what they use. */
export function collect(draw: (frame: number) => React.ReactElement, runtime: Omit<Runtime, 'mode' | 'record'>): Usage {
	const pictures: Usage['pictures'] = new Map();
	const sounds: MediaUse[] = [];
	const record = (u: MediaUse) => {
		if (u.picture) {
			const p = pictures.get(u.src) ?? {frames: new Set<number>(), transparent: false};
			p.frames.add(Math.max(0, Math.round(u.seconds * runtime.fps)));
			p.transparent ||= Boolean(u.transparent);
			pictures.set(u.src, p);
		}
		if (u.volume > 0) sounds.push(u);
	};
	const rt: Runtime = {...runtime, mode: 'collect', record};
	for (let f = 0; f < runtime.durationInFrames; f++) renderToStaticMarkup(<FrameRoot runtime={rt} frame={f}>{draw(f)}</FrameRoot>);
	return {pictures, sounds};
}

const round = (x: number, places = 4) => Math.round(x * 10 ** places) / 10 ** places;

/** Drop points a straight line through their neighbours already gives. */
function simplify(points: {t: number; v: number}[]): {t: number; v: number}[] {
	if (points.length <= 2) return points.length === 2 && Math.abs(points[0].v - points[1].v) < 1e-3 ? [points[0]] : points;
	const out = [points[0]];
	for (let i = 1; i < points.length - 1; i++) {
		const a = out[out.length - 1];
		const b = points[i];
		const c = points[i + 1];
		const expected = a.v + ((c.v - a.v) * (b.t - a.t)) / (c.t - a.t);
		if (Math.abs(expected - b.v) > 1e-3) out.push(b);
	}
	out.push(points[points.length - 1]);
	return out.length === 2 && Math.abs(out[0].v - out[1].v) < 1e-3 ? [out[0]] : out;
}

/**
 * Sound uses joined into clips: one clip while the same file plays on, frame after frame, at its own pace.
 * `durations` (seconds per file) wraps looping sound (music) back to its start.
 */
export function audioClips(sounds: MediaUse[], fps: number, durations: Record<string, number> = {}): AudioClip[] {
	const bySrc = new Map<string, MediaUse[]>();
	for (const s of sounds) {
		const dur = durations[s.src];
		const u = s.loop && dur ? {...s, seconds: s.seconds % dur} : s;
		bySrc.set(u.src, [...(bySrc.get(u.src) ?? []), u]);
	}
	const clips: AudioClip[] = [];
	for (const [src, uses] of bySrc) {
		uses.sort((a, b) => a.frame - b.frame || a.seconds - b.seconds);
		// Two copies of one file on the same frame (overlapping pieces) become separate clips: take them in turn.
		const open: MediaUse[][] = [];
		for (const u of uses) {
			const run = open.find((r) => {
				const last = r[r.length - 1];
				return u.frame === last.frame + 1 && Math.abs(u.seconds - (last.seconds + last.step)) < 0.5 / fps && Math.abs(u.step - last.step) < 1e-6;
			});
			if (run) run.push(u);
			else open.push([u]);
		}
		for (const run of open) {
			if (!run[0].step) continue; // a held frame makes no sound
			const first = run[0];
			clips.push({
				id: '',
				src,
				start: round(first.frame / fps),
				duration: round(run.length / fps),
				mediaStart: round(first.seconds),
				rate: round(first.step * fps),
				volume: simplify(run.map((u) => ({t: round((u.frame - first.frame) / fps), v: round(u.volume, 3)}))),
			});
		}
	}
	clips.sort((a, b) => a.start - b.start || a.src.localeCompare(b.src));
	return clips.map((c, i) => ({...c, id: `snd${i}`}));
}
