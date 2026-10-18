import {describe, expect, it} from 'vitest';
import {aroundElements, artFor, faceBox, faceClearance, PARTICLE_COUNT, passElements, rand} from './Around';
import {builtinIcon} from './icons';
import {depthAt, modeAt} from './layout';
import {normalizePlan, type Graphic} from './plan';

const base = {source: {path: 'v.mp4', width: 1920, height: 1080, fps: 30, duration: 20}};
const W = 1080;
const H = 1920;
const face = {x: 540, y: 700};
const g = (type: Graphic['type'], props: Record<string, unknown>): Graphic => ({id: 'o1', type, start: 2, end: 7, props, anchor: 'auto'});

describe('effects around the speaker', () => {
	it('need depth on and a cut-out, and never open a panel', () => {
		const orbit = g('orbit', {items: ['🔥', 'A']});
		const on = normalizePlan({...base, graphics: [orbit], style: {depth: {enabled: true}}});
		const d = depthAt(on, 3, 'speaker', true)!;
		expect(d.around.map((x) => x.id)).toEqual(['o1']);
		expect(d.behind).toEqual([]);
		expect(d.cutout).toBe(true);
		expect(depthAt(on, 3, 'split', true)!.around).toEqual([]);
		expect(modeAt(on.layout, on.graphics, 3).mode).toBe('speaker');
	});

	it('orbit puts the far side behind the speaker and the near side in front', () => {
		const els = aroundElements(g('orbit', {items: ['a', 'b', 'c', 'd']}), 3, face, W, H);
		expect(els).toHaveLength(4);
		const box = faceBox(face, W, H);
		const behind = passElements(els, 'behind', box);
		const front = passElements(els, 'front', box);
		expect(behind.length).toBeGreaterThan(0);
		expect(behind.length + front.length).toBeLessThanOrEqual(4);
		expect(behind.every((e) => e.depth < 0.5)).toBe(true);
	});

	it('fly-out items start behind the head and come out in front', () => {
		const fx = g('fly_out', {items: ['💰']});
		const early = aroundElements(fx, 2.1, face, W, H)[0];
		const late = aroundElements(fx, 3.0, face, W, H)[0];
		expect(early.depth).toBeLessThan(0.5);
		expect(late.depth).toBeGreaterThanOrEqual(0.5);
		expect(aroundElements(fx, 5, face, W, H)).toEqual([]); // its 1.4 s life is over
	});

	it('front elements never cover the face', () => {
		const box = faceBox(face, W, H);
		expect(faceClearance({x: face.x, y: face.y, size: 100}, box)).toBe(0);
		expect(faceClearance({x: 100, y: 1700, size: 100}, box)).toBe(1);
		const onFace = {key: 'k', x: face.x, y: face.y, size: 80, depth: 0.9, opacity: 1, rotate: 0, content: {kind: 'item' as const, art: {viewBox: '0 0 100 100', body: ''}}};
		expect(passElements([onFace], 'front', box)).toEqual([]);
		expect(passElements([onFace], 'all', box)).toEqual([]);
		for (let t = 2; t < 7; t += 0.1) {
			for (const type of ['orbit', 'fly_out', 'particles'] as const) {
				for (const e of passElements(aroundElements(g(type, {items: ['a', 'b', 'c'], kind: 'bokeh'}), t, face, W, H), 'front', box)) {
					const inside = e.x > box.x0 && e.x < box.x1 && e.y > box.y0 && e.y < box.y1;
					expect(inside && e.opacity > 0.01).toBe(false);
				}
			}
		}
	});

	it('items are drawn graphics: Claude\'s drawing, else a built-in icon, never the raw text', () => {
		const drawn = {viewBox: '0 0 400 400', body: '<circle r="9"/>'};
		const fx = g('orbit', {items: ['stack of coins', 'rocket launch', '🔥'], art: {'stack of coins': drawn, 'rocket launch': null}});
		expect(artFor(fx, 'stack of coins', 0, '#f00')).toEqual(drawn);
		const rocket = artFor(fx, 'rocket launch', 1, '#f00');
		expect(rocket.viewBox).toBe('0 0 100 100');
		expect(rocket.body).toBe(builtinIcon('rocket', '#f00'));
		expect(rocket.body).toContain('#f00');
		expect(artFor(fx, '🔥', 2, '#f00').body).not.toContain('🔥');
		expect(builtinIcon('supper', '#f00')).toBe(builtinIcon('zzz', '#f00', 0)); // no match inside words
	});

	it('particles are a pure function of time', () => {
		const p = g('particles', {kind: 'confetti'});
		expect(aroundElements(p, 4, face, W, H)).toEqual(aroundElements(p, 4, face, W, H));
		expect(aroundElements(p, 4, face, W, H)).toHaveLength(PARTICLE_COUNT.confetti);
		expect(rand('x', 1)).toBeGreaterThanOrEqual(0);
		expect(rand('x', 1)).toBeLessThan(1);
	});
});
