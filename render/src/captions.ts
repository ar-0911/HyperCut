// Pure caption logic: grouping words into lines and per-word animation state.

import type {CaptionAnimation, Word} from './plan';

export type Group = {words: Word[]; start: number; end: number};

const SENTENCE_END = /[.!?…]["')\]]*$/;
/** A clause end: a line may stop here once it has two words. */
const CLAUSE_END = /[,;:—–]["')\]]*$/;
/** Words that lean on the next one: a line never ends on them when the next word can join it (ADR 0617). */
const LEANS_FORWARD = new Set(
	'a an the of to in on at by for with from into onto and but or nor if than my your his her its our their'.split(' '),
);
const bare = (text: string) => text.toLowerCase().replace(/[^a-z']/g, '');
/** A pause this long starts a new line even if the line is not full. */
const BREAK_GAP = 0.7;
/** How long a line lingers after its last word, capped by the gap to the next line. */
const HOLD = 0.25;

/**
 * Group words into lines by phrase (ADR 0617): at most `perLine` words and `maxChars` characters, breaking early at
 * sentence ends, long pauses and (from two words) clause ends, never ending a full line on a word that leans on
 * the next ("the", "of", "and"): that word starts the next line instead, and never leaving a sentence's last word
 * alone on a line (the full line takes one word more).
 */
export function groupWords(words: Word[], perLine: number, maxChars = Infinity): Group[] {
	const groups: Group[] = [];
	let cur: Word[] = [];
	const flush = (keep = 0) => {
		const line = cur.slice(0, cur.length - keep);
		if (line.length) groups.push({words: line, start: line[0].start, end: line[line.length - 1].end});
		cur = cur.slice(cur.length - keep);
	};
	const leans = (x: Word) => LEANS_FORWARD.has(bare(x.text));
	const solid = (ws: Word[]) => ws.some((x) => !leans(x));
	// Move a last word that leans on the next one to the next line, if what stays still has a word of its own.
	const carry = (ws: Word[]) => (ws.length > 1 && leans(ws[ws.length - 1]) && solid(ws.slice(0, -1)) ? 1 : 0);
	const chars = (ws: Word[]) => ws.reduce((n, x) => n + x.text.length, 0) + Math.max(0, ws.length - 1);
	words.forEach((w, i) => {
		// Too long with this word: end the line before it, unless that would leave only words leaning forward.
		if (cur.length && chars([...cur, w]) > maxChars && solid(cur)) flush(carry(cur));
		cur.push(w);
		const next = words[i + 1];
		const pause = next && next.start - w.end > BREAK_GAP;
		if (SENTENCE_END.test(w.text) || pause || (cur.length >= 2 && CLAUSE_END.test(w.text))) flush();
		// A sentence's last word joins the full line rather than sit alone on the next one, if it fits.
		else if (cur.length >= perLine && !(next && SENTENCE_END.test(next.text) && perLine >= 3 && cur.length === perLine && chars([...cur, next]) <= maxChars))
			flush(next ? carry(cur) : 0);
	});
	flush();
	return groups;
}

/** About how many characters fit on one caption line at this size (960 px of a 1080-wide frame). */
export function lineChars(size: number, uppercase: boolean, width = 960): number {
	return Math.max(8, Math.floor(width / (size * (uppercase ? 0.6 : 0.52))));
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
