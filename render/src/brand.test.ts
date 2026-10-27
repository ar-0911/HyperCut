import {describe, expect, it} from 'vitest';
import {endCardFrames, logoBox, musicVolumes, speaking} from './brand';
import {normalizePlan} from './plan';
import {buildTimeline} from './timing';

const plan = (brand: object = {}, words = [{text: 'hi', start: 2, end: 3}]) =>
	normalizePlan({source: {path: 'x.mp4', width: 1920, height: 1080, fps: 30, duration: 10}, transcript: {words}, brand});

describe('music ducking', () => {
	const p = plan({music: 'brand-music.mp3', music_volume: 0.4, duck: 0.25});
	const tl = buildTimeline(p.segments, p.source.duration, 30);
	it('knows when someone speaks, with a little padding', () => {
		const talk = speaking(p, tl);
		expect(talk[30]).toBe(false);
		expect(talk[2 * 30 - 5]).toBe(true); // 0.17 s before the word
		expect(talk[75]).toBe(true);
		expect(talk[4 * 30]).toBe(false);
	});
	it('dips under speech and comes back up, fading in and out', () => {
		const v = musicVolumes(p, tl);
		expect(v).toHaveLength(300);
		expect(v[0]).toBe(0);
		expect(v[50]).toBeCloseTo(0.4, 2);
		expect(v[85]).toBeLessThan(0.12); // under the word
		expect(v[200]).toBeCloseTo(0.4, 2); // back up
		expect(v[299]).toBeLessThan(0.02); // faded out at the end
	});
	it('follows the timeline through a cold open', () => {
		const cold = plan({music: 'm.mp3'}, [{text: 'a', start: 6, end: 7}]);
		cold.segments = [{start: 6, end: 7, reason: 'hook'}, {start: 0, end: 10, reason: 'body'}];
		const t2 = buildTimeline(cold.segments, 10, 30);
		const talk = speaking(cold, t2);
		expect(talk[10]).toBe(true); // the hook
		expect(talk[30 + 3 * 30]).toBe(false);
		expect(talk[30 + 6 * 30 + 15]).toBe(true); // the same word again in the body
	});
});

describe('end card and logo', () => {
	it('shows the end card over the last seconds only when there is a line', () => {
		expect(endCardFrames(plan(), 300)).toBeNull();
		expect(endCardFrames(plan({end_card: 'Follow for more', end_card_seconds: 2}), 300)).toEqual({from: 240, frames: 60});
	});
	it('puts the logo in its corner inside the margins', () => {
		expect(logoBox('top_right', 0.2, 1080, 1920)).toEqual({left: 1080 - 65 - 216, top: 134, width: 216});
		expect(logoBox('bottom_left', 0.2, 1080, 1920).left).toBe(65);
	});
});
