import {describe, expect, it} from 'vitest';
import {cropRect, placeGraphic, pointInOutput, reframeAt, zoomAt} from './layout';

describe('reframeAt', () => {
	const keys = [
		{t: 0, cx: 0.4, cy: 0.4},
		{t: 10, cx: 0.6, cy: 0.5},
	];
	it('centers with no keys', () => expect(reframeAt([], 3)).toEqual({cx: 0.5, cy: 0.5}));
	it('interpolates and holds the ends', () => {
		expect(reframeAt(keys, 5)).toEqual({cx: 0.5, cy: 0.45});
		expect(reframeAt(keys, -1)).toEqual({cx: 0.4, cy: 0.4});
		expect(reframeAt(keys, 99)).toEqual({cx: 0.6, cy: 0.5});
	});
	it('tolerates unsorted keys', () => expect(reframeAt([...keys].reverse(), 5).cx).toBeCloseTo(0.5));
});

describe('cropRect', () => {
	const out = {width: 1080, height: 1920};
	it('covers the output from a landscape source', () => {
		const r = cropRect({width: 1920, height: 1080}, out, 0.5, 0.5);
		expect(r.height).toBeCloseTo(1920);
		expect(r.width).toBeCloseTo((1920 * 1920) / 1080);
		expect(r.left).toBeCloseTo(-(r.width - 1080) / 2);
		expect(r.top).toBeCloseTo(0);
	});
	it('puts the subject mid-frame and clamps at the edges', () => {
		const src = {width: 1920, height: 1080};
		const mid = cropRect(src, out, 0.6, 0.5);
		expect(pointInOutput(mid, 0.6, 0.5).x).toBeCloseTo(540);
		const edge = cropRect(src, out, 0.02, 0.5);
		expect(edge.left).toBe(-0);
		const far = cropRect(src, out, 1, 0.5);
		expect(far.left).toBeCloseTo(-(far.width - 1080));
	});
	it('handles a source already 9:16', () => {
		const r = cropRect({width: 1080, height: 1920}, out, 0.3, 0.3);
		expect(r).toMatchObject({left: -0, top: -0});
	});
});

describe('zoomAt', () => {
	it('is 1 outside zooms', () => expect(zoomAt([{start: 1, end: 2, scale: 1.3, ease: 'snap'}], 3)).toBe(1));
	it('snaps almost immediately', () => {
		expect(zoomAt([{start: 1, end: 2, scale: 1.3, ease: 'snap'}], 1.2)).toBeCloseTo(1.3);
	});
	it('eases in and out', () => {
		const z = [{start: 0, end: 2, scale: 1.2, ease: 'ease_in_out' as const}];
		expect(zoomAt(z, 0)).toBeCloseTo(1);
		expect(zoomAt(z, 1)).toBeCloseTo(1.2);
		expect(zoomAt(z, 1.99)).toBeLessThan(1.01);
	});
	it('ramps linearly', () => {
		expect(zoomAt([{start: 0, end: 2, scale: 1.4, ease: 'linear'}], 1)).toBeCloseTo(1.2);
	});
	it('takes the strongest overlap', () => {
		const z = [
			{start: 0, end: 4, scale: 1.1, ease: 'snap' as const},
			{start: 1, end: 3, scale: 1.5, ease: 'snap' as const},
		];
		expect(zoomAt(z, 2)).toBeCloseTo(1.5);
	});
});

describe('placeGraphic', () => {
	it('honors an anchor that is clear of the face', () => {
		expect(placeGraphic('top', 0.5, 'bottom')).toBe('top');
	});
	it('moves off a face in the way', () => {
		// face high in frame: the top band collides; the bottom band would sit on the captions
		expect(placeGraphic('top', 0.15, 'bottom')).not.toBe('top');
		expect(placeGraphic('auto', 0.15, 'bottom')).toBe('center');
	});
	it('auto avoids a centered face', () => {
		expect(placeGraphic('auto', 0.5, 'bottom')).toBe('top');
		expect(placeGraphic('center', 0.5, 'bottom')).toBe('top');
	});
	it('avoids the caption band', () => {
		expect(placeGraphic('auto', 0.4, 'top')).toBe('bottom');
	});
	it('still returns something when nothing is clear', () => {
		expect(['top', 'center', 'bottom']).toContain(placeGraphic('auto', 0.45, 'middle'));
	});
});
