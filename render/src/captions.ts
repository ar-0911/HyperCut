// Pure caption logic: grouping words into lines and per-word animation state.

import type {CaptionAnimation, Word} from './plan';

export type Group = {words: Word[]; start: number; end: number};

const SENTENCE_END = /[.!?…]["')\]]*$/;
/** A pause this long starts a new line even if the line is not full. */
const BREAK_GAP = 0.7;
/** How long a line lingers after its last word, capped by the gap to the next line. */
const HOLD = 0.25;

/** Group words into lines of at most `perLine`, breaking early at sentence ends and long pauses. */
export function groupWords(words: Word[], perLine: number): Group[] {
	const groups: Group[] = [];
	let cur: Word[] = [];
	const flush = () => {
		if (cur.length) groups.push({words: cur, start: cur[0].start, end: cur[cur.length - 1].end});
		cur = [];
	};
	words.forEach((w, i) => {
		cur.push(w);
		const next = words[i + 1];
		if (cur.length >= perLine || SENTENCE_END.test(w.text) || (next && next.start - w.end > BREAK_GAP)) flush();
	});
	flush();
	return groups;
}

/** The group on screen at source time t, with its index; null between lines. */
export function groupAt(groups: Group[], t: number): {group: Group; index: number} | null {
	for (let i = groups.length - 1; i >= 0; i--) {
		const g = groups[i];
		if (t < g.start) continue;
		const nextStart = groups[i + 1]?.start ?? Infinity;
		const until = Math.min(g.end + HOLD, nextStart);
		return t < until ? {group: g, index: i} : null;
	}
	return null;
}

export type WordState = {
	visible: boolean;
	active: boolean;
	scale: number;
	/** Vertical offset in units of the font size (negative = up). */
	lift: number;
	opacity: number;
};

const easeOutBack = (k: number) => {
	const c1 = 1.70158;
	const c3 = c1 + 1;
	return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2);
};
const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

/** Seconds a word's entrance animation takes. */
export const ENTER = 0.18;

/** Animation state of word `i` of a group at source time t. */
export function wordState(animation: CaptionAnimation, group: Group, i: number, t: number): WordState {
	const w = group.words[i];
	const spoken = t >= w.start;
	const next = group.words[i + 1];
	const isCurrent = spoken && (!next || t < next.start);
	const since = t - w.start;
	const base: WordState = {visible: true, active: isCurrent, scale: 1, lift: 0, opacity: 1};

	switch (animation) {
		case 'karaoke':
			// Whole line is there from the start; the highlight walks across it.
			return base;
		case 'typewriter':
			// Words appear as they are spoken and stay.
			return {...base, visible: spoken, opacity: spoken ? clamp01(since / 0.06) : 0};
		case 'pop': {
			// Whole line shown; the current word punches in from 60%.
			const k = isCurrent ? easeOutBack(clamp01(since / ENTER)) : 1;
			return {...base, scale: isCurrent ? 0.6 + 0.5 * k : 1};
		}
		case 'bounce': {
			// Each word drops in from above with overshoot as it is spoken, then rests.
			const k = spoken ? easeOutBack(clamp01(since / (ENTER * 1.5))) : 0;
			return {
				...base,
				visible: spoken,
				lift: -0.6 * (1 - k),
				opacity: clamp01(since / 0.05),
				scale: 0.85 + 0.15 * k,
			};
		}
	}
}
