import {describe, expect, it} from 'vitest';
import {groupAt, groupWords, wordState} from './captions';
import type {Word} from './plan';

const w = (text: string, start: number, end: number): Word => ({text, start, end});
const words = [
	w('Most', 0.2, 0.45),
	w('people', 0.45, 0.8),
	w('waste', 0.8, 1.1),
	w('ten', 1.1, 1.35),
	w('hours.', 1.35, 1.7),
	w('Here', 3.0, 3.2),
];

describe('groupWords', () => {
	it('groups by words_per_line', () => {
		const g = groupWords(words, 3);
		expect(g.map((x) => x.words.map((y) => y.text))).toEqual([['Most', 'people', 'waste'], ['ten', 'hours.'], ['Here']]);
	});
	it('breaks at sentence end and long gaps even when the line is short', () => {
		const g = groupWords(words, 8);
		expect(g.map((x) => x.words.length)).toEqual([5, 1]);
		const gap = groupWords([w('a', 0, 0.2), w('b', 2, 2.2)], 8);
		expect(gap).toHaveLength(2);
	});
	it('supports one word per line and empty input', () => {
		expect(groupWords(words, 1)).toHaveLength(6);
		expect(groupWords([], 3)).toEqual([]);
	});
});

describe('groupAt', () => {
	const g = groupWords(words, 3);
	it('shows a line from its first word until just after its last', () => {
		expect(groupAt(g, 0.1)).toBeNull();
		expect(groupAt(g, 0.5)?.index).toBe(0);
		expect(groupAt(g, 1.05)?.index).toBe(0); // within the hold... until next group starts at 1.1
		expect(groupAt(g, 1.2)?.index).toBe(1);
	});
	it('hides the line after a long pause', () => {
		expect(groupAt(g, 2.5)).toBeNull();
		expect(groupAt(g, 3.1)?.index).toBe(2);
	});
});

describe('wordState', () => {
	const group = groupWords(words, 3)[0];
	it('karaoke highlights only the current word', () => {
		const at = (t: number) => [0, 1, 2].map((i) => wordState('karaoke', group, i, t).active);
		expect(at(0.3)).toEqual([true, false, false]);
		expect(at(0.9)).toEqual([false, false, true]);
	});
	it('typewriter reveals words as spoken', () => {
		expect([0, 1, 2].map((i) => wordState('typewriter', group, i, 0.5).visible)).toEqual([true, true, false]);
	});
	it('pop scales the current word up from 60%', () => {
		expect(wordState('pop', group, 0, 0.2).scale).toBeCloseTo(0.6);
		expect(wordState('pop', group, 0, 0.2 + 0.18).scale).toBeCloseTo(1.1);
		expect(wordState('pop', group, 1, 0.3).scale).toBe(1);
	});
	it('bounce drops words in and settles', () => {
		expect(wordState('bounce', group, 0, 0.1).visible).toBe(false);
		expect(wordState('bounce', group, 0, 0.2).lift).toBeLessThan(0);
		expect(wordState('bounce', group, 0, 0.9).lift).toBeCloseTo(0);
		expect(wordState('bounce', group, 0, 0.9).scale).toBeCloseTo(1);
	});
});
