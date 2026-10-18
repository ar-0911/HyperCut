import {describe, expect, it} from 'vitest';
import {buildTimeline, clipSpan, frameToSource, isKept, mediaRuns, segmentAtFrame, sourceToFrames} from './timing';

const fps = 30;
const cold = buildTimeline(
	[
		{start: 0.2, end: 2.2, reason: 'hook'},
		{start: 0, end: 2.4, reason: 'body'},
		{start: 5.9, end: 12, reason: 'body'},
	],
	12,
	fps,
);

describe('buildTimeline', () => {
	it('treats empty segments as the whole source', () => {
		const tl = buildTimeline([], 10, fps);
		expect(tl.durationInFrames).toBe(300);
		expect(frameToSource(tl, 0)).toBe(0);
		expect(frameToSource(tl, 150)).toBeCloseTo(5);
	});

	it('lays segments back to back with frame-exact lengths', () => {
		expect(cold.segments.map((s) => [s.outFrom, s.frames])).toEqual([
			[0, 60],
			[60, 72],
			[132, 183],
		]);
		expect(cold.durationInFrames).toBe(315);
	});

	it('gives tiny segments at least one frame', () => {
		const tl = buildTimeline([{start: 1, end: 1.001, reason: 'body'}], 5, fps);
		expect(tl.durationInFrames).toBe(1);
	});
});

describe('frameToSource', () => {
	it('maps through segment boundaries', () => {
		expect(frameToSource(cold, 0)).toBeCloseTo(0.2);
		expect(frameToSource(cold, 59)).toBeCloseTo(0.2 + 59 / 30);
		expect(frameToSource(cold, 60)).toBeCloseTo(0); // cold open ends, body restarts at 0
		expect(frameToSource(cold, 132)).toBeCloseTo(5.9); // jump over the cut
	});

	it('is null outside the output', () => {
		expect(frameToSource(cold, -1)).toBeNull();
		expect(frameToSource(cold, cold.durationInFrames)).toBeNull();
		expect(segmentAtFrame(cold, 9999)).toBeNull();
	});
});

describe('sourceToFrames', () => {
	it('returns both occurrences of a hooked moment', () => {
		const hits = sourceToFrames(cold, 1);
		expect(hits).toHaveLength(2);
		expect(hits[0]).toBeCloseTo(24);
		expect(hits[1]).toBeCloseTo(90);
	});

	it('returns nothing for cut time', () => {
		expect(sourceToFrames(cold, 4)).toEqual([]);
		expect(isKept(cold, 4)).toBe(false);
		expect(isKept(cold, 6)).toBe(true);
	});
});

describe('clipSpan', () => {
	it('clips a span that crosses a cut and repeats it for the hook', () => {
		const parts = clipSpan(cold, {start: 2.0, end: 6.5});
		expect(parts).toHaveLength(3);
		expect(parts[0]).toMatchObject({segmentIndex: 0});
		expect(parts[0].endFrame).toBeCloseTo(60);
		expect(parts[1].startFrame).toBeCloseTo(60 + 60);
		expect(parts[1].endFrame).toBeCloseTo(132);
		expect(parts[2].startFrame).toBeCloseTo(132);
		expect(parts[2].endFrame).toBeCloseTo(132 + 0.6 * 30);
	});

	it('drops a span that lies entirely in a cut', () => {
		expect(clipSpan(cold, {start: 3, end: 5})).toEqual([]);
	});
});

describe('mediaRuns', () => {
	const fps = 30;
	// Hook 10-12 first, then body 0-5 and 5.5-20 (a filler cut at 5-5.5).
	const tl = buildTimeline(
		[
			{start: 10, end: 12, reason: 'hook'},
			{start: 0, end: 5, reason: 'body'},
			{start: 5.5, end: 20, reason: 'body'},
		],
		20,
		fps,
	);

	it('joins pieces across a small cut so the clip plays straight through', () => {
		expect(mediaRuns(tl, {start: 4, end: 7})).toEqual([{from: 6 * fps, frames: 2.5 * fps, offset: 0}]);
	});

	it('gives the cold-open copy its own run', () => {
		const runs = mediaRuns(tl, {start: 11, end: 13});
		expect(runs).toEqual([
			{from: 1 * fps, frames: 1 * fps, offset: 0},
			{from: Math.round((2 + 5 + 5.5) * fps), frames: 2 * fps, offset: 0},
		]);
	});

	it('is empty for a span that was cut', () => {
		expect(mediaRuns(tl, {start: 5.1, end: 5.4})).toEqual([]);
	});
});
