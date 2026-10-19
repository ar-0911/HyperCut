import {describe, expect, it} from 'vitest';
import {animate, boundsOf, fitScene, HERO, spring, type SceneObject} from './Motion';

describe('spring', () => {
	it('starts at 0, overshoots a little and settles at 1', () => {
		expect(spring(0)).toBe(0);
		expect(spring(1)).toBe(1);
		const peak = Math.max(...Array.from({length: 50}, (_, i) => spring(i / 50)));
		expect(peak).toBeGreaterThan(1);
		expect(peak).toBeLessThan(1.25);
	});
});

describe('animate', () => {
	it('enters from below and lands on its position', () => {
		const o: SceneObject = {shape: 'sphere', position: [1, 2, 0], anim: [{type: 'enter', from: 'below', at: 0, dur: 0.5}]};
		expect(animate(o, 0).position[1]).toBeCloseTo(-2);
		expect(animate(o, 5).position).toEqual([1, 2, 0]);
	});
});

describe('boundsOf and fitScene', () => {
	it('measures shapes at their resting place, children included', () => {
		const o: SceneObject = {shape: 'group', position: [1, 0, 0], scale: 2, children: [{shape: 'box', size: [1, 2, 1], position: [0, 1, 0]}]};
		expect(boundsOf(o)).toEqual([
			[0, 0, -1],
			[2, 4, 1],
		]);
	});
	it('turned objects take the box around their turned corners', () => {
		const [min, max] = boundsOf({shape: 'box', size: [2, 1, 1], rotation: [0, 0, 90]});
		expect(max[1] - min[1]).toBeCloseTo(2);
		expect(max[0] - min[0]).toBeCloseTo(1);
	});
	it('scales any scene into the hero box under the title', () => {
		for (const size of [0.2, 3, 12]) {
			const fit = fitScene([{shape: 'box', size: [size, size, 0.1]}], {orbit: 0, push: 0}, 3);
			const h = size * fit.scale;
			expect(h).toBeLessThanOrEqual(HERO.y[1] - HERO.y[0] + 1e-6);
			expect(fit.offset[1] + h / 2).toBeLessThanOrEqual(HERO.y[1] + 1e-6);
			expect(fit.floor).toBeCloseTo(fit.offset[1] - h / 2);
		}
		expect(fitScene([], undefined, 3).scale).toBe(1);
	});
	it('a helix spinning in place is measured round its axis', () => {
		const [min, max] = boundsOf({shape: 'helix', radius: 1, height: 6, anim: [{type: 'spin', axis: 'y'}]});
		expect(max[1] - min[1]).toBeCloseTo(6);
		expect(max[0]).toBeGreaterThanOrEqual(1);
	});
});
