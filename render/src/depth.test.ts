import {describe, expect, it} from 'vitest';
import {backgroundFilter, parallaxTransform, replacesBackground, titleSize} from './Depth';
import {depthAt, modeAt} from './layout';
import {normalizePlan} from './plan';

const base = {source: {path: 'v.mp4', width: 1920, height: 1080, fps: 30, duration: 20}};
const title = {id: 'b1', type: 'kinetic_text', start: 2, end: 4, props: {text: 'TEN X'}, layer: 'behind'};

describe('green-screen effects', () => {
	it('are off unless the plan asks and a cut-out exists', () => {
		const off = normalizePlan({...base, graphics: [title]});
		expect(off.style.depth.enabled).toBe(false);
		expect(depthAt(off, 3, 'speaker', true)).toBeNull();
		const on = normalizePlan({...base, graphics: [title], style: {depth: {enabled: true}}});
		expect(depthAt(on, 3, 'speaker', false)).toBeNull();
		const d = depthAt(on, 3, 'speaker', true)!;
		expect(d.behind.map((g) => g.id)).toEqual(['b1']);
		expect(d.cutout).toBe(true);
		expect(depthAt(on, 10, 'speaker', true)!.cutout).toBe(false); // original background, nothing behind
		expect(depthAt(on, 3, 'visual', true)).toBeNull();
		expect(depthAt(on, 3, 'split', true)!.behind).toEqual([]);
	});

	it('uses the background span, else the style default', () => {
		const plan = normalizePlan({
			...base,
			backgrounds: [{start: 5, end: 8, kind: 'gradient', parallax: 0.5}],
			style: {depth: {enabled: true, background: 'blur'}},
		});
		expect(depthAt(plan, 6, 'speaker', true)!.background.kind).toBe('gradient');
		expect(depthAt(plan, 9, 'speaker', true)!.background.kind).toBe('blur');
		expect(depthAt(plan, 9, 'speaker', true)!.cutout).toBe(true);
	});

	it('never opens the split panel for a graphic behind the speaker', () => {
		const plan = normalizePlan({...base, graphics: [title]});
		expect(modeAt(plan.layout, plan.graphics, 3).mode).toBe('speaker');
	});

	it('fits titles on one line and treats backgrounds by kind', () => {
		expect(titleSize('TEN X', 1080)).toBe(Math.round(1080 * 0.36));
		expect(titleSize('MAKES LIFE EASIER', 1080) * 17 * 0.48).toBeLessThan(1080 * 0.93);
		expect(backgroundFilter('original')).toBeUndefined();
		expect(backgroundFilter('blur')).toMatch(/blur/);
		expect(replacesBackground('media') && !replacesBackground('dim')).toBe(true);
		expect(parallaxTransform(0, 3)).toBe('none');
	});
});
