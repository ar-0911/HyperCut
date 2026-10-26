import {describe, expect, it} from 'vitest';
import {graphicStyle} from './Graphics';
import {stillTransform} from './HyperCut';
import type {Graphic, GraphicsStyle} from './plan';

const style = {accent_color: '#FFE600'} as GraphicsStyle;
const g = (type: Graphic['type'], props: Record<string, unknown>): Graphic => ({id: 'x', type, start: 0, end: 1, props, anchor: 'auto', layer: 'front'});

describe('stills', () => {
	it('every move stays scaled past the frame, from start to end', () => {
		for (const move of ['push_in', 'pull_out', 'pan_left', 'pan_right', 'rise', undefined]) {
			for (const k of [0, 0.5, 1]) {
				const scale = Number(/scale\(([\d.]+)/.exec(stillTransform(move, k))?.[1]);
				expect(scale).toBeGreaterThanOrEqual(1.02);
			}
		}
		expect(stillTransform('pan_left', 0)).not.toEqual(stillTransform('pan_left', 1));
	});
});

describe('graphic colour', () => {
	it('uses its own colour only when it is a hex colour', () => {
		expect(graphicStyle(g('kinetic_text', {accent: '#3366FF'}), style).accent_color).toBe('#3366FF');
		expect(graphicStyle(g('kinetic_text', {accent: 'red; x'}), style)).toBe(style);
	});
});
