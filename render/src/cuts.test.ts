import {describe, expect, it} from 'vitest';
import {cutAt, cutStyles, cutWindows} from './cuts';
import {normalizePlan} from './plan';
import {buildTimeline} from './timing';

const plan = (cuts: object[]) =>
	normalizePlan({
		source: {path: 'x.mp4', width: 1920, height: 1080, fps: 30, duration: 60},
		segments: [
			{start: 40, end: 44, reason: 'hook'},
			{start: 0, end: 30},
		],
		cuts,
	});

describe('cutWindows', () => {
	it('places each transition where its source time first plays, holding the frame before', () => {
		const p = plan([{at: 0, kind: 'drop', length: 0.6}, {at: 10, kind: 'whip', length: 0.4}]);
		const w = cutWindows(p, buildTimeline(p.segments, 60, 30));
		expect(w).toEqual([
			{kind: 'drop', from: 120, frames: 18, hold: 119},
			{kind: 'whip', from: 420, frames: 12, hold: 419},
		]);
	});
	it('drops transitions in cut footage, at the very start or overlapping another', () => {
		const p = plan([{at: 35, kind: 'push'}, {at: 40, kind: 'zoom'}, {at: 10, kind: 'whip', length: 1}, {at: 10.2, kind: 'drop'}]);
		const w = cutWindows(p, buildTimeline(p.segments, 60, 30));
		expect(w.map((x) => x.kind)).toEqual(['whip']);
	});
});

describe('cutAt and cutStyles', () => {
	const w = [{kind: 'drop' as const, from: 100, frames: 10, hold: 99}];
	it('reports progress inside the window only', () => {
		expect(cutAt(w, 99)).toBeNull();
		expect(cutAt(w, 100)?.k).toBeCloseTo(0.1);
		expect(cutAt(w, 109)?.k).toBeCloseTo(1);
		expect(cutAt(w, 110)).toBeNull();
	});
	it('moves the held frame fully out of view by the end', () => {
		expect(cutStyles('drop', 1, 1080, 1920).out.transform).toContain('translateY(2208px)');
		expect(cutStyles('whip', 1, 1080, 1920).out.transform).toBe('translateX(-1080px)');
		expect(cutStyles('whip', 1, 1080, 1920).in.transform).toBe('translateX(0px)');
		expect(cutStyles('push', 1, 1080, 1920).out.transform).toBe('translateY(-1920px)');
		expect(cutStyles('zoom', 1, 1080, 1920).out.opacity).toBe(0);
	});
});
