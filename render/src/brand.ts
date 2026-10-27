// Pure brand-kit logic (ADR 0026): when someone is speaking, the music level per frame, the end card window and
// where the logo sits. No React.

import type {EditPlan, LogoCorner} from './plan';
import {frameToSource, type Timeline} from './timing';

/** Seconds around each word that still count as speech, so the music doesn't swell between words. */
export const SPEECH_PAD = 0.25;
/** Seconds the music takes to dip under speech, and to come back up after it. */
export const DUCK_ATTACK = 0.12;
export const DUCK_RELEASE = 0.5;
/** Seconds the music fades in at the start. */
export const MUSIC_FADE_IN = 0.6;

/** Whether someone is speaking at each output frame. */
export function speaking(plan: EditPlan, tl: Timeline): boolean[] {
	const words = [...plan.transcript.words].sort((a, b) => a.start - b.start);
	const out = new Array<boolean>(tl.durationInFrames).fill(false);
	let j = 0;
	for (let f = 0; f < tl.durationInFrames; f++) {
		const t = frameToSource(tl, f);
		if (t === null) continue;
		// Frames mostly move forward in source time; step back when the timeline jumps back (a cold open).
		while (j > 0 && words[j - 1].end + SPEECH_PAD > t) j--;
		while (j < words.length && words[j].end + SPEECH_PAD < t) j++;
		out[f] = j < words.length && words[j].start - SPEECH_PAD <= t;
	}
	return out;
}

/** Music volume (0..1) per output frame: `music_volume` in pauses, `music_volume * duck` under speech, eased,
 * faded in at the start and out with the reel's fade (or its end card). */
export function musicVolumes(plan: EditPlan, tl: Timeline): number[] {
	const {fps} = tl;
	const {music_volume: base, duck} = plan.brand;
	const talk = speaking(plan, tl);
	const attack = 1 - Math.exp(-1 / (DUCK_ATTACK * fps));
	const release = 1 - Math.exp(-1 / (DUCK_RELEASE * fps));
	const total = tl.durationInFrames;
	const fadeOut = Math.max(plan.style.transitions.fade_out, 0.5) * fps;
	const vols: number[] = [];
	let level = talk[0] ? base * duck : base;
	for (let f = 0; f < total; f++) {
		const target = talk[f] ? base * duck : base;
		level += (target - level) * (target < level ? attack : release);
		const fadeIn = Math.min(1, f / (MUSIC_FADE_IN * fps));
		const tail = Math.min(1, Math.max(0, (total - f) / fadeOut));
		vols.push(Math.max(0, level * fadeIn * tail));
	}
	return vols;
}

/** The output frames the end card is on screen, or null when the kit has no end card. */
export function endCardFrames(plan: EditPlan, total: number): {from: number; frames: number} | null {
	const text = plan.brand.end_card.trim();
	if (!text) return null;
	const frames = Math.min(total, Math.round(plan.brand.end_card_seconds * plan.output.fps));
	return {from: total - frames, frames};
}

/** Where the logo sits (output pixels): a corner, inside the platforms' safe margins. */
export function logoBox(corner: LogoCorner, size: number, width: number, height: number): {left: number; top: number; width: number} {
	const w = Math.round(size * width);
	const marginX = Math.round(width * 0.06);
	// Shorts players put their own title at the top and buttons at the bottom: stay a little inside both.
	const top = corner.startsWith('top') ? Math.round(height * 0.07) : Math.round(height * 0.8);
	const left = corner.endsWith('left') ? marginX : width - marginX - w;
	return {left, top, width: w};
}
