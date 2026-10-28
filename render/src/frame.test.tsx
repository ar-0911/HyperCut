import React from 'react';
import {describe, expect, it} from 'vitest';
import {audioClips, collect} from './collect';
import {Audio, Freeze, frameUrl, interpolate, OffthreadVideo, Sequence, spring, useCurrentFrame, type MediaUse} from './frame';
import {extractArgs, frameRuns} from './hf/extract';
import {audioTag, compositionHtml} from './hf/html';
import {normalizePlan} from './plan';

const base = {fps: 30, width: 1080, height: 1920};

describe('interpolate', () => {
	it('maps piecewise and extends by default', () => {
		expect(interpolate(5, [0, 10], [0, 100])).toBe(50);
		expect(interpolate(15, [0, 10], [0, 100])).toBe(150);
		expect(interpolate(15, [0, 10, 20], [0, 100, 0])).toBe(50);
	});
	it('clamps when asked', () => {
		expect(interpolate(-3, [0, 10], [1, 2], {extrapolateLeft: 'clamp'})).toBe(1);
		expect(interpolate(30, [0, 10], [1, 2], {extrapolateRight: 'clamp'})).toBe(2);
	});
	it('applies easing inside a piece', () => {
		expect(interpolate(5, [0, 10], [0, 100], {easing: (t) => t * t})).toBe(25);
	});
	it('refuses ranges that do not rise', () => {
		expect(() => interpolate(1, [0, 0], [0, 1])).toThrow();
	});
});

describe('spring', () => {
	it('starts at rest and settles at its end', () => {
		expect(spring({frame: 0, fps: 30})).toBe(0);
		expect(spring({frame: 300, fps: 30})).toBeCloseTo(1, 2);
	});
	it('overshoots when lightly damped, not when heavily damped', () => {
		const light = Array.from({length: 60}, (_, f) => spring({frame: f, fps: 30, config: {damping: 5}}));
		expect(Math.max(...light)).toBeGreaterThan(1.05);
		const heavy = Array.from({length: 60}, (_, f) => spring({frame: f, fps: 30, config: {damping: 200}}));
		expect(Math.max(...heavy)).toBeLessThanOrEqual(1);
	});
	it('is retimed to settle within durationInFrames', () => {
		const k = (f: number) => spring({frame: f, fps: 30, config: {damping: 200}, durationInFrames: 18});
		expect(k(9)).toBeGreaterThan(0.5);
		expect(k(18)).toBeGreaterThan(0.99);
		expect(spring({frame: 10, fps: 30, from: 40, to: 0, config: {damping: 200}, durationInFrames: 10})).toBeCloseTo(0, 0);
	});
});

const Probe: React.FC<{out: number[]}> = ({out}) => {
	out.push(useCurrentFrame());
	return null;
};

describe('sequences and freezes (dry run)', () => {
	it('counts frames from a sequence start and hides it outside', () => {
		const seen: number[] = [];
		collect(() => (
			<Sequence from={3} durationInFrames={2}>
				<Probe out={seen} />
			</Sequence>
		), {...base, durationInFrames: 8});
		expect(seen).toEqual([0, 1]);
	});
	it('holds a frozen frame', () => {
		const seen: number[] = [];
		collect(() => (
			<Freeze frame={7}>
				<Probe out={seen} />
			</Freeze>
		), {...base, durationInFrames: 3});
		expect(seen).toEqual([7, 7, 7]);
	});
	it('lists the video frames drawn and the sound they make', () => {
		const usage = collect(() => (
			<Sequence from={10} durationInFrames={20} layout="none">
				<OffthreadVideo src="a.mp4" startFrom={60} volume={(f) => (f < 10 ? 1 : 0.5)} />
			</Sequence>
		), {...base, durationInFrames: 40});
		const frames = [...usage.pictures.get('a.mp4')!.frames].sort((x, y) => x - y);
		expect(frames).toEqual(Array.from({length: 20}, (_, i) => 60 + i));
		const clips = audioClips(usage.sounds, 30);
		expect(clips).toHaveLength(1);
		expect(clips[0]).toMatchObject({src: 'a.mp4', start: 0.3333, duration: 0.6667, mediaStart: 2, rate: 1});
		expect(clips[0].volume[0]).toEqual({t: 0, v: 1});
		expect(clips[0].volume.at(-1)!.v).toBe(0.5);
	});
	it('records a frozen or muted video as silent, but still needs its frame', () => {
		const usage = collect(() => (
			<>
				<Freeze frame={0}>
					<OffthreadVideo src="b.mp4" startFrom={90} />
				</Freeze>
				<OffthreadVideo src="c.mp4" muted />
			</>
		), {...base, durationInFrames: 5});
		expect([...usage.pictures.get('b.mp4')!.frames]).toEqual([90]);
		expect(usage.pictures.get('c.mp4')!.frames.size).toBe(5);
		expect(usage.sounds).toHaveLength(0);
	});
	it('wraps looping music at its length', () => {
		const usage = collect(() => <Audio src="m.mp3" loop volume={0.4} />, {...base, durationInFrames: 90});
		const clips = audioClips(usage.sounds, 30, {'m.mp3': 2});
		expect(clips.map((c) => [c.start, c.duration, c.mediaStart])).toEqual([
			[0, 2, 0],
			[2, 1, 0],
		]);
		expect(clips[0].volume).toEqual([{t: 0, v: 0.4}]);
	});
});

describe('sound clips', () => {
	const use = (frame: number, seconds: number, volume = 1): MediaUse => ({src: 's.mp4', frame, seconds, step: 1 / 30, volume, picture: true});
	it('starts a new clip at a cut in the source', () => {
		const clips = audioClips([use(0, 5), use(1, 5 + 1 / 30), use(2, 9), use(3, 9 + 1 / 30)], 30);
		expect(clips.map((c) => c.mediaStart)).toEqual([5, 9]);
	});
	it('keeps two overlapping copies apart', () => {
		const clips = audioClips([use(0, 1), use(0, 4), use(1, 1 + 1 / 30), use(1, 4 + 1 / 30)], 30);
		expect(clips).toHaveLength(2);
		expect(clips.every((c) => c.duration === 0.0667)).toBe(true);
	});
	it('writes HyperFrames audio tags, with a volume envelope only when the level moves', () => {
		const flat = audioTag({id: 'snd0', src: 'assets/a.mp4', start: 1, duration: 2, mediaStart: 3, rate: 1, volume: [{t: 0, v: 0.5}]});
		expect(flat).toContain('data-volume="0.5"');
		expect(flat).not.toContain('data-automation');
		const moving = audioTag({id: 'snd1', src: 'a.mp4', start: 0, duration: 1, mediaStart: 0, rate: 1.1, volume: [{t: 0, v: 0}, {t: 1, v: 1}]});
		expect(moving).toContain('data-automation=');
		expect(moving).toContain('data-playback-rate="1.1"');
	});
});

describe('frames to extract', () => {
	it('joins nearby frames into runs', () => {
		expect(frameRuns([5, 1, 2, 3, 40, 41, 3])).toEqual([
			{first: 1, last: 5},
			{first: 40, last: 41},
		]);
		expect(frameRuns([0, 30], 12)).toEqual([
			{first: 0, last: 0},
			{first: 30, last: 30},
		]);
	});
	it('names each frame by its index', () => {
		const args = extractArgs('in.mp4', {first: 30, last: 59}, 30, 'out', 'jpg', false);
		expect(args).toEqual(expect.arrayContaining(['-ss', '1.000000', '-frames:v', '30', '-start_number', '30', 'out/%d.jpg']));
		expect(extractArgs('m.webm', {first: 0, last: 0}, 30, 'o', 'png', true).slice(3, 5)).toEqual(['-c:v', 'libvpx-vp9']);
		expect(frameUrl({'a.mp4': {dir: 'frames/0', fps: 30, ext: 'jpg'}}, 'a.mp4', 1.01)).toBe('frames/0/30.jpg');
	});
});

describe('the composition page', () => {
	it('holds the plan safely and sizes the root from it', () => {
		const plan = normalizePlan({source: {path: 'x.mp4', width: 1920, height: 1080, fps: 30, duration: 4}, transcript: {words: [{text: '</script><b>', start: 1, end: 2}]}});
		const html = compositionHtml({
			config: {mode: 'render', props: {plan, videoSrc: 's.mp4'}, fps: 30, width: 1080, height: 1920, durationInFrames: 120, staticBase: 'assets/'},
			audio: [],
			scripts: ['hypercut-page.js'],
		});
		expect(html).toContain('data-duration="4"');
		expect(html).toContain('data-width="1080"');
		expect(html).not.toContain('</script><b>');
		expect(html).toContain('<script src="hypercut-page.js"></script>');
	});
});
