import {describe, expect, it} from 'vitest';
import {editorialScale, JCUT_FRAMES, jcutFrames, PUNCH_IN, punchedIn, sameShot, SETTLE} from './editorial';
import {tailFrames} from './HyperCut';
import {normalizePlan} from './plan';
import {buildTimeline} from './timing';

const plan = (shots: number[], extra: object = {}) =>
	normalizePlan({
		source: {path: 'v.mp4', width: 1920, height: 1080, fps: 30, duration: 60},
		segments: [
			{start: 0, end: 5},
			{start: 6, end: 10},
			{start: 10, end: 14}, // continues the piece before: a split, not a cut
			{start: 15, end: 20},
			{start: 22, end: 30},
		],
		reframe: {keys: [], shots},
		...extra,
	});
const tl = (p: ReturnType<typeof plan>) => buildTimeline(p.segments, p.source.duration, 30, 1);

describe('editorial cuts', () => {
	it('is the default for new plans', () => {
		expect(plan([]).style.transitions.style).toBe('editorial');
	});

	it('alternates a punch-in across jump cuts of the same shot and resets on a new shot', () => {
		const p = plan([21]);
		const t = tl(p);
		expect(sameShot(p, t, 0)).toBe(true);
		expect(sameShot(p, t, 3)).toBe(false); // a new shot starts in the skipped part
		expect(punchedIn(p, t)).toEqual([false, true, true, false, false]);
		expect(editorialScale(p, t, 1, 7, punchedIn(p, t))).toBeCloseTo(PUNCH_IN);
	});

	it('settles a new shot in from slightly closer', () => {
		const p = plan([21, 26]);
		const t = tl(p);
		const punched = punchedIn(p, t);
		expect(editorialScale(p, t, 4, 22, punched)).toBeCloseTo(SETTLE.scale); // a jump onto another shot
		expect(editorialScale(p, t, 4, 22 + SETTLE.seconds, punched)).toBeCloseTo(1);
		expect(editorialScale(p, t, 4, 26.1, punched)).toBeGreaterThan(1); // a hard cut inside the piece
		expect(editorialScale(p, t, 0, 2, punched)).toBe(1);
	});

	it('holds the outgoing picture a few frames as the next sound starts (J-cut), only where it can', () => {
		const p = plan([5.05]);
		const t = tl(p);
		expect(jcutFrames(p, t, 0)).toBe(0); // the frames after the piece belong to another shot
		expect(jcutFrames(p, t, 1)).toBe(0); // a split, not a cut
		expect(jcutFrames(p, t, 2)).toBe(JCUT_FRAMES);
		expect(tailFrames(p, t, 2)).toBe(JCUT_FRAMES);
		expect(tailFrames(p, t, 4)).toBe(0); // the last piece
		const covered = plan([], {cuts: [{at: 15, kind: 'drop', length: 0.5}]});
		expect(jcutFrames(covered, tl(covered), 2)).toBe(0); // an animated transition takes this cut
		const smooth = plan([], {style: {transitions: {style: 'smooth'}}});
		expect(jcutFrames(smooth, tl(smooth), 2)).toBe(0);
		expect(editorialScale(smooth, tl(smooth), 1, 7, punchedIn(smooth, tl(smooth)))).toBe(1);
	});
});
