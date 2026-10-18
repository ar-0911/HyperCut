// Pure source-time <-> output-frame mapping. No React, no Remotion.
//
// The plan lists `segments` (pieces of source kept, in play order). An empty list means the whole
// source. The same source time can appear twice (cold-open hook), so source -> output is one-to-many
// while output -> source is a function.

import type {Segment, Span} from './plan';

export type TimelineSegment = {
	index: number;
	/** Source seconds. */
	start: number;
	end: number;
	/** Output frames, [outFrom, outFrom + frames). */
	outFrom: number;
	frames: number;
	reason: Segment['reason'];
};

export type Timeline = {
	fps: number;
	segments: TimelineSegment[];
	durationInFrames: number;
};

/** Frame-exact timeline: each segment gets round(duration * fps) frames (at least 1), no drift. */
export function buildTimeline(segments: Segment[], sourceDuration: number, fps: number): Timeline {
	const kept: Segment[] = segments.length ? segments : [{start: 0, end: sourceDuration, reason: 'body'}];
	let cursor = 0;
	const out: TimelineSegment[] = kept.map((s, index) => {
		const frames = Math.max(1, Math.round((s.end - s.start) * fps));
		const seg = {index, start: s.start, end: s.end, outFrom: cursor, frames, reason: s.reason};
		cursor += frames;
		return seg;
	});
	return {fps, segments: out, durationInFrames: cursor};
}

export function segmentAtFrame(tl: Timeline, frame: number): TimelineSegment | null {
	if (frame < 0 || frame >= tl.durationInFrames) return null;
	// Segments are few (tens); linear scan is fine and keeps this obviously correct.
	for (const s of tl.segments) if (frame < s.outFrom + s.frames) return s;
	return null;
}

/** Source time (seconds) shown at an output frame, or null past the end. */
export function frameToSource(tl: Timeline, frame: number): number | null {
	const seg = segmentAtFrame(tl, frame);
	if (!seg) return null;
	return Math.min(seg.end, seg.start + (frame - seg.outFrom) / tl.fps);
}

/** Every output frame (fractional) at which a source time is on screen. Empty if it was cut. */
export function sourceToFrames(tl: Timeline, t: number): number[] {
	const hits: number[] = [];
	for (const s of tl.segments) {
		if (t >= s.start && t <= s.end) hits.push(s.outFrom + (t - s.start) * tl.fps);
	}
	return hits;
}

export type OutputSpan = {startFrame: number; endFrame: number; segmentIndex: number};

/** The parts of a source span that survive the cuts, as output frame ranges (clipped at cut edges). */
export function clipSpan(tl: Timeline, span: Span): OutputSpan[] {
	const res: OutputSpan[] = [];
	for (const s of tl.segments) {
		const a = Math.max(span.start, s.start);
		const b = Math.min(span.end, s.end);
		if (b > a) {
			res.push({
				startFrame: s.outFrom + (a - s.start) * tl.fps,
				endFrame: s.outFrom + (b - s.start) * tl.fps,
				segmentIndex: s.index,
			});
		}
	}
	return res;
}

export function isKept(tl: Timeline, t: number): boolean {
	return tl.segments.some((s) => t >= s.start && t < s.end);
}

export type MediaRun = {
	/** Output frame the run starts at, and its length. */
	from: number;
	frames: number;
	/** Seconds into the graphic (source time since graphic.start) at which the run starts. */
	offset: number;
};

/**
 * Where an imported clip plays on the output: one run per stretch of output where the graphic is on screen
 * without a jump back in source time. Pieces that follow each other in the output and move forward in
 * source (body segments with a filler cut between them) join one run, so B-roll plays smoothly over small
 * cuts instead of skipping. A cold-open copy of the span is its own run.
 */
export function mediaRuns(tl: Timeline, span: Span): MediaRun[] {
	const runs: (MediaRun & {lastEnd: number})[] = [];
	for (const s of tl.segments) {
		const a = Math.max(span.start, s.start);
		const b = Math.min(span.end, s.end);
		if (b <= a) continue;
		const from = s.outFrom + (a - s.start) * tl.fps;
		const to = s.outFrom + (b - s.start) * tl.fps;
		const prev = runs[runs.length - 1];
		if (prev && Math.abs(prev.from + prev.frames - from) < 1 && a >= prev.lastEnd - 1e-6) {
			prev.frames = to - prev.from;
			prev.lastEnd = b;
		} else {
			runs.push({from, frames: to - from, offset: a - span.start, lastEnd: b});
		}
	}
	return runs.map(({from, frames, offset}) => ({from: Math.round(from), frames: Math.max(1, Math.round(frames)), offset}));
}
