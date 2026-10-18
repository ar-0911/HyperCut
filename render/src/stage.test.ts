import {describe, expect, it} from 'vitest';
import {depthAt, modeAt, PULL_BACK, pullAt} from './layout';
import {normalizePlan} from './plan';
import {cardBoxes, chartPoints, freeSide, pulledFace, scopeIds, splitHeadline, stageFootageFilter} from './Stage';

const base = {source: {path: 'v.mp4', width: 1920, height: 1080, fps: 30, duration: 20}};
const chart = {id: 's1', type: 'chart', start: 2, end: 6, props: {headline: '20 YEARS', values: [1, 4, 9]}};
const cards = {id: 's2', type: 'card_stack', start: 8, end: 11, props: {cards: [{title: 'Nurse'}]}};

describe('stage graphics', () => {
	it('need depth on and a cut-out, never open a panel, and pull the speaker back for charts', () => {
		const on = normalizePlan({...base, graphics: [chart, cards], style: {depth: {enabled: true}}});
		const d = depthAt(on, 4, 'speaker', true)!;
		expect(d.stage.map((g) => g.id)).toEqual(['s1']);
		expect(d.cutout).toBe(true);
		expect(d.pull).toBe(1);
		expect(depthAt(on, 4, 'speaker', false)).toBeNull();
		expect(depthAt(on, 4, 'split', true)!.stage).toEqual([]);
		expect(modeAt(on.layout, on.graphics, 4).mode).toBe('speaker');
		expect(pullAt(on, 2)).toBe(0);
		expect(pullAt(on, 2.2)).toBeGreaterThan(0);
		expect(pullAt(on, 2.2)).toBeLessThan(1);
		expect(pullAt(on, 9)).toBe(0); // cards don't pull the speaker back
		const off = normalizePlan({...base, graphics: [chart]});
		expect(depthAt(off, 4, 'speaker', true)).toBeNull();
	});

	it('lays cards down the side away from the face', () => {
		expect(freeSide(800, 1080)).toBe('left');
		expect(freeSide(300, 1080)).toBe('right');
		const boxes = cardBoxes(3, 'right', 1080, 1920);
		expect(boxes).toHaveLength(3);
		expect(boxes.every((b) => b.x + b.w <= 1080 && b.x > 540)).toBe(true);
		expect(boxes[1].y).toBeGreaterThan(boxes[0].y + boxes[0].h);
	});

	it('pulls the face down and in by the pull amount', () => {
		const f = pulledFace({x: 600, y: 600}, 1920, 1);
		expect(f.scale).toBeCloseTo(1 - PULL_BACK);
		expect(f.y).toBeCloseTo(1920 - 1320 * (1 - PULL_BACK));
		expect(pulledFace({x: 600, y: 600}, 1920, 0).y).toBe(600);
	});

	it('charts, headlines and drawings', () => {
		expect(chartPoints([0, 5, 10], 100, 50)).toEqual([{x: 0, y: 50}, {x: 50, y: 25}, {x: 100, y: 0}]);
		expect(splitHeadline('20 YEARS')).toEqual(['20', 'YEARS']);
		expect(splitHeadline('$4.5M saved')).toEqual(['$4.5M', 'saved']);
		expect(splitHeadline('KEEP GROWING')).toEqual(['', 'KEEP GROWING']);
		expect(scopeIds('<linearGradient id="g"/><rect fill="url(#g)"/><use href="#g"/>', 'a-')).toBe(
			'<linearGradient id="a-g"/><rect fill="url(#a-g)"/><use href="#a-g"/>',
		);
		const g = (type: string) => ({id: 'x', type, start: 0, end: 1, props: {}, anchor: 'auto'}) as never;
		expect(stageFootageFilter([g('card_stack')])).toContain('blur');
		expect(stageFootageFilter([g('chart')])).toBeUndefined();
	});
});
