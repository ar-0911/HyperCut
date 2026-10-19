// Animated transitions (ADR 0613): where they fall on the output timeline and how the two layers move.
// The last frame before the cut is held and moved away (dropped, whipped, pushed through, slid up) while
// the incoming footage already plays under or beside it. Pure: no React, no Remotion.

import type {CSSProperties} from 'react';
import type {CutKind, EditPlan} from './plan';
import {sourceToFrames, type Timeline} from './timing';

export type CutWindow = {kind: CutKind; from: number; frames: number; hold: number};

/** Output frames each transition covers, in order, never overlapping or running past the end. */
export function cutWindows(plan: EditPlan, tl: Timeline): CutWindow[] {
	const out: CutWindow[] = [];
	const sorted = plan.cuts
		.map((c) => ({c, f: sourceToFrames(tl, c.at).map(Math.round).find((f) => f >= 1)}))
		.filter((x): x is {c: EditPlan['cuts'][number]; f: number} => x.f !== undefined)
		.sort((a, b) => a.f - b.f);
	for (const {c, f} of sorted) {
		const frames = Math.max(2, Math.min(Math.round(c.length * tl.fps), tl.durationInFrames - f));
		if (frames < 2 || (out.length && f < out[out.length - 1].from + out[out.length - 1].frames)) continue;
		out.push({kind: c.kind, from: f, frames, hold: f - 1});
	}
	return out;
}

/** The transition playing at an output frame and how far along it is (0..1), or null. */
export function cutAt(windows: CutWindow[], frame: number): (CutWindow & {k: number}) | null {
	const w = windows.find((x) => frame >= x.from && frame < x.from + x.frames);
	return w ? {...w, k: (frame - w.from + 1) / w.frames} : null;
}

const easeInOut = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2);
const easeOut = (x: number) => 1 - (1 - x) ** 3;

/** CSS for the held outgoing frame and the live incoming footage at progress k. */
export function cutStyles(kind: CutKind, k: number, width: number, height: number): {out: CSSProperties; in: CSSProperties} {
	const e = easeInOut(k);
	switch (kind) {
		case 'drop': {
			// The frame falls away under gravity, tipping slightly, and the next shot settles in behind it.
			const g = k * k;
			return {
				out: {transform: `translateY(${g * height * 1.15}px) rotate(${g * 7}deg)`, transformOrigin: '0% 100%', boxShadow: '0 -30px 80px rgba(0,0,0,0.45)'},
				in: {transform: `scale(${1.08 - 0.08 * easeOut(k)})`},
			};
		}
		case 'whip': {
			// A fast pan: both frames travel together, smeared most in the middle of the move.
			const blur = Math.sin(Math.PI * k) * 26;
			return {
				out: {transform: `translateX(${-e * width}px)`, filter: `blur(${blur}px)`},
				in: {transform: `translateX(${(1 - e) * width}px)`, filter: `blur(${blur}px)`},
			};
		}
		case 'zoom':
			// Pushing through the old shot toward the viewer, landing on the new one.
			return {
				out: {transform: `scale(${1 + 1.6 * e})`, opacity: 1 - easeOut(k), filter: `blur(${e * 18}px)`},
				in: {transform: `scale(${1.3 - 0.3 * easeOut(k)})`, filter: `blur(${(1 - easeOut(k)) * 10}px)`},
			};
		case 'push':
		default:
			// The new shot slides up and pushes the old one out of the top.
			return {
				out: {transform: `translateY(${-e * height}px)`},
				in: {transform: `translateY(${(1 - e) * height}px)`},
			};
	}
}
