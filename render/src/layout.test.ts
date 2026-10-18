import {describe, expect, it} from 'vitest';
import {
	CAPTION_Y,
	captionY,
	cropRect,
	layoutAt,
	modeAt,
	panelAt,
	placeGraphic,
	pointInOutput,
	reframeAt,
	sceneAt,
	SPLIT,
	SPLIT_IN,
	zoomAt,
} from './layout';
import {normalizePlan, type Graphic, type LayoutSpan} from './plan';

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

describe('layoutAt', () => {
	const spans: LayoutSpan[] = [
		{start: 2, end: 4, mode: 'split'},
		{start: 4, end: 6, mode: 'split'},
		{start: 6, end: 8, mode: 'visual'},
	];
	it('is speaker outside every span', () => {
		expect(layoutAt([], 3)).toEqual({mode: 'speaker', enter: Infinity});
		expect(layoutAt(spans, 1).mode).toBe('speaker');
		expect(layoutAt(spans, 8).mode).toBe('speaker');
	});
	it('reports the mode and time since the span started', () => {
		expect(layoutAt(spans, 2.5)).toEqual({mode: 'split', enter: 0.5});
		expect(layoutAt(spans, 7)).toEqual({mode: 'visual', enter: 1});
	});
	it('treats back-to-back spans of one mode as one', () => {
		expect(layoutAt(spans, 5)).toEqual({mode: 'split', enter: 3});
		expect(layoutAt([...spans].reverse(), 5).enter).toBe(3);
	});
});

describe('modeAt', () => {
	const g = (id: string, type: Graphic['type'], start: number, end: number): Graphic => ({id, type, start, end, props: {}, anchor: 'auto'});
	const spans: LayoutSpan[] = [{start: 0, end: 10, mode: 'split'}];
	it('falls back to speaker with no visual on screen', () => {
		expect(modeAt(spans, [g('a', 'lower_third', 0, 10)], 3).mode).toBe('speaker');
		expect(modeAt(spans, [g('a', 'illustration', 4, 6)], 3).mode).toBe('speaker');
	});
	it('counts enter from the visual that arrived mid-span', () => {
		expect(modeAt(spans, [g('a', 'illustration', 4, 6)], 4.1)).toEqual({mode: 'split', enter: expect.closeTo(0.1)});
	});
	it('does not restart across touching visuals', () => {
		const gs = [g('a', 'kinetic_text', 1, 3), g('b', 'stat_card', 3, 5)];
		expect(modeAt(spans, gs, 4).enter).toBeCloseTo(3);
	});
	it('opens the split panel for a visual during a speaker span', () => {
		expect(modeAt([], [g('a', 'kinetic_text', 2, 4)], 2.5)).toEqual({mode: 'split', enter: expect.closeTo(0.5)});
		expect(modeAt([], [g('a', 'emoji_burst', 2, 4)], 2.5).mode).toBe('speaker');
	});
	it('never counts from before the span', () => {
		expect(modeAt([{start: 5, end: 9, mode: 'visual'}], [g('a', 'illustration', 0, 9)], 6).enter).toBeCloseTo(1);
	});
});

describe('panelAt', () => {
	it('is the full frame outside split', () => {
		expect(panelAt('speaker', 0, 1920)).toEqual({top: 0, height: 1920});
		expect(panelAt('visual', 0, 1920)).toEqual({top: 0, height: 1920});
	});
	it('slides from full frame to the bottom half', () => {
		expect(panelAt('split', 0, 1920).top).toBe(0);
		const mid = panelAt('split', SPLIT_IN / 2, 1920).top;
		expect(mid).toBeGreaterThan(0);
		expect(mid).toBeLessThan(SPLIT * 1920);
		expect(panelAt('split', SPLIT_IN, 1920)).toEqual({top: 960, height: 960});
		expect(panelAt('split', 99, 1920)).toEqual({top: 960, height: 960});
	});
});

describe('captionY', () => {
	it('follows the style in speaker mode', () => {
		expect(captionY('speaker', 'top')).toBe(CAPTION_Y.top);
		expect(captionY('speaker', 'bottom')).toBe(CAPTION_Y.bottom);
	});
	it('sits on the seam in split and at the bottom over a visual', () => {
		expect(captionY('split', 'top')).toBe(SPLIT);
		expect(captionY('visual', 'top')).toBe(CAPTION_Y.bottom);
	});
});

describe('sceneAt (zoom about the face)', () => {
	const base = {
		source: {path: 's.mp4', width: 3414, height: 1920, fps: 30, duration: 20},
		reframe: {keys: [{t: 0, cx: 0.5, cy: 0.25}]},
		zooms: [{start: 0, end: 20, scale: 1.2, ease: 'snap'}],
		graphics: [{id: 'v', type: 'illustration', start: 10, end: 20, props: {layers: []}}],
		layout: [{start: 10, end: 20, mode: 'split'}],
	};
	const plan = normalizePlan(base);
	it('zooms about the face in speaker mode, and the face does not move', () => {
		const s = sceneAt(plan, 1);
		expect(s.mode).toBe('speaker');
		expect(s.origin.x).toBeCloseTo(540);
		expect(s.origin.y).toBeCloseTo(0.25 * 1920);
		expect(s.faceY).toBeCloseTo(0.25);
	});
	it('puts the face in the bottom panel in split mode', () => {
		const s = sceneAt(plan, 15);
		expect(s.mode).toBe('split');
		expect(s.panel).toEqual({top: 960, height: 960});
		expect(s.rect.height).toBeCloseTo(960);
		expect(s.origin.y).toBeCloseTo(0.25 * 960);
		expect(s.face.y).toBeCloseTo(960 + 0.25 * 960);
		expect(s.captionY).toBe(SPLIT);
	});
	it('moves the captions with the seam while the panel slides', () => {
		const y = sceneAt(plan, 10 + SPLIT_IN / 2).captionY;
		expect(y).toBeGreaterThan(SPLIT);
		expect(y).toBeLessThan(CAPTION_Y.bottom);
		expect(sceneAt(plan, 10).captionY).toBeCloseTo(CAPTION_Y.bottom);
	});
	it('keeps the panel covered: scaling >= 1 about a point inside it', () => {
		for (const t of [1, 10.1, 15]) {
			const s = sceneAt(plan, t);
			expect(s.origin.x).toBeGreaterThanOrEqual(0);
			expect(s.origin.x).toBeLessThanOrEqual(1080);
			expect(s.origin.y).toBeGreaterThanOrEqual(0);
			expect(s.origin.y).toBeLessThanOrEqual(s.panel.height);
			// Scaled crop still spans the panel on every side.
			const z = s.zoom;
			expect(s.origin.x + (s.rect.left - s.origin.x) * z).toBeLessThanOrEqual(0.001);
			expect(s.origin.y + (s.rect.top - s.origin.y) * z).toBeLessThanOrEqual(0.001);
			expect(s.origin.x + (s.rect.left + s.rect.width - s.origin.x) * z).toBeGreaterThanOrEqual(1080 - 0.001);
			expect(s.origin.y + (s.rect.top + s.rect.height - s.origin.y) * z).toBeGreaterThanOrEqual(s.panel.height - 0.001);
		}
	});
	it('keeps the old defaults without a face track', () => {
		const s = sceneAt(normalizePlan({...base, reframe: {keys: []}, layout: []}), 1);
		expect(s.origin).toEqual({x: 540, y: 960});
		expect(s.faceY).toBe(0.4);
	});
});
