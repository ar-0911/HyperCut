// Pure timeline model for the editor: what blocks sit on which track (in REEL seconds) and the edits you
// can make to them. Every edit returns a new plan; nothing here touches React or the network.
//
// The plan stores source seconds; the reel is what you watch. `buildTimeline` from the renderer maps
// between them, so the editor and the final render can never disagree about where something is.

import {groupWords} from '@render/captions';
import {isAroundType, isVisualType} from '@render/layout';
import type {EditPlan, Graphic, GraphicType, LayoutMode, Segment} from '@render/plan';
import {buildTimeline, frameToSource, sourceToFrames, type Timeline} from '@render/timing';

export type TrackId = 'visuals' | 'overlays' | 'layout' | 'zooms' | 'video' | 'captions';

export const TRACKS: {id: TrackId; label: string; hint: string}[] = [
	{id: 'visuals', label: 'Visuals', hint: 'Illustrations, your footage, text cards'},
	{id: 'overlays', label: 'Overlays', hint: 'Emoji, name tags, progress bar'},
	{id: 'layout', label: 'Layout', hint: 'Speaker, split screen or full-screen visual'},
	{id: 'zooms', label: 'Zooms', hint: 'Push-ins on the face'},
	{id: 'video', label: 'Video', hint: 'The parts of your footage that are kept'},
	{id: 'captions', label: 'Captions', hint: 'Subtitles, line by line'},
];

export type ItemRef =
	| {kind: 'graphic'; id: string}
	| {kind: 'zoom'; index: number}
	| {kind: 'layout'; index: number}
	| {kind: 'segment'; index: number}
	| {kind: 'caption'; first: number; last: number};

export type Piece = {from: number; to: number};

export type Item = {
	key: string;
	ref: ItemRef;
	track: TrackId;
	label: string;
	/** Source seconds. */
	start: number;
	end: number;
	/** Where it shows in the reel (seconds). Two pieces when it sits inside a cold-open hook. */
	pieces: Piece[];
	movable: boolean;
	tone: string;
};

export const refKey = (r: ItemRef): string => {
	switch (r.kind) {
		case 'graphic':
			return `g:${r.id}`;
		case 'caption':
			return `c:${r.first}`;
		default:
			return `${r.kind[0]}:${r.index}`;
	}
};

export const timelineOf = (plan: EditPlan): Timeline =>
	buildTimeline(plan.segments, plan.source.duration, plan.output.fps, plan.style.pacing.speed);

export const reelDuration = (plan: EditPlan): number => timelineOf(plan).durationInFrames / plan.output.fps;

/** Source time at reel second t (clamped into the reel). */
export function toSource(tl: Timeline, t: number): number {
	const frame = Math.min(Math.max(0, t * tl.fps), tl.durationInFrames - 1e-3);
	return frameToSource(tl, frame) ?? 0;
}

/** Reel pieces of a source span (merging pieces that touch, e.g. across a filler cut). */
export function piecesOf(tl: Timeline, start: number, end: number): Piece[] {
	const out: Piece[] = [];
	for (const s of tl.segments) {
		const a = Math.max(start, s.start);
		const b = Math.min(end, s.end);
		if (b <= a) continue;
		const from = s.outFrom / tl.fps + (a - s.start) / tl.speed;
		const to = s.outFrom / tl.fps + (b - s.start) / tl.speed;
		const prev = out[out.length - 1];
		// Segments are whole frames long, so touching pieces can be up to a frame apart in seconds.
		if (prev && Math.abs(prev.to - from) <= 1 / tl.fps + 1e-6) prev.to = to;
		else out.push({from, to});
	}
	return out;
}

const str = (v: unknown) => (v === undefined || v === null ? '' : String(v));

export const GRAPHIC_NAMES: Record<GraphicType, string> = {
	illustration: 'Illustration',
	media: 'Your footage',
	kinetic_text: 'Big text',
	stat_card: 'Stat card',
	list_build: 'List',
	lower_third: 'Name tag',
	emoji_burst: 'Emoji',
	progress_bar: 'Progress bar',
	orbit: 'Orbit',
	fly_out: 'Fly out',
	particles: 'Particles',
};

export function graphicLabel(g: Graphic): string {
	const p = g.props;
	const text =
		g.type === 'media'
			? str(p.label) || 'clip'
			: g.type === 'stat_card'
				? `${str(p.value)} ${str(p.label)}`.trim()
				: g.type === 'list_build'
					? str(p.title)
					: g.type === 'emoji_burst'
						? str(p.emoji)
						: g.type === 'orbit' || g.type === 'fly_out'
							? (Array.isArray(p.items) ? p.items.map(str).join(' ') : '')
							: g.type === 'particles'
								? str(p.kind)
								: str(p.title) || str(p.text);
	return text || GRAPHIC_NAMES[g.type];
}

export const LAYOUT_NAMES: Record<LayoutMode, string> = {speaker: 'Speaker', split: 'Split screen', visual: 'Full-screen visual'};

/** Every block on the timeline, track by track. */
export function buildItems(plan: EditPlan): Item[] {
	const tl = timelineOf(plan);
	const items: Item[] = [];
	const push = (ref: ItemRef, track: TrackId, label: string, start: number, end: number, movable: boolean, tone: string) => {
		const pieces = piecesOf(tl, start, end);
		if (pieces.length) items.push({key: refKey(ref), ref, track, label, start, end, pieces, movable, tone});
	};
	for (const g of plan.graphics) {
		const visual = isVisualType(g.type);
		push({kind: 'graphic', id: g.id}, visual ? 'visuals' : 'overlays', graphicLabel(g), g.start, g.end, true, g.type === 'media' ? 'media' : visual ? 'visual' : 'overlay');
	}
	plan.layout.forEach((l, index) => push({kind: 'layout', index}, 'layout', LAYOUT_NAMES[l.mode], l.start, l.end, true, `layout-${l.mode}`));
	plan.zooms.forEach((z, index) => push({kind: 'zoom', index}, 'zooms', `${Math.round((z.scale - 1) * 100)}%`, z.start, z.end, true, 'zoom'));
	const segs = plan.segments.length ? plan.segments : [{start: 0, end: plan.source.duration, reason: 'body' as const}];
	segs.forEach((s, index) => {
		const out = tl.segments[index];
		items.push({
			key: refKey({kind: 'segment', index}),
			ref: {kind: 'segment', index},
			track: 'video',
			label: s.reason === 'hook' ? 'Hook' : '',
			start: s.start,
			end: s.end,
			pieces: [{from: out.outFrom / tl.fps, to: (out.outFrom + out.frames) / tl.fps}],
			movable: false,
			tone: s.reason === 'hook' ? 'hook' : 'clip',
		});
	});
	// Caption lines as the viewer sees them: words grouped the way the renderer groups them.
	const indexed = plan.transcript.words.map((w, i) => ({...w, speaker: String(i)}));
	for (const group of groupWords(indexed, plan.style.caption.words_per_line)) {
		const first = Number(group.words[0].speaker);
		const last = Number(group.words[group.words.length - 1].speaker);
		push({kind: 'caption', first, last}, 'captions', group.words.map((w) => w.text).join(' '), group.start, group.end, false, 'caption');
	}
	return items;
}

// ---------- edits ----------

const round = (n: number) => Math.round(n * 1000) / 1000;
const MIN_LEN = 0.2;

function clampSpan(plan: EditPlan, start: number, end: number): [number, number] {
	const d = plan.source.duration;
	let a = Math.max(0, Math.min(start, d - MIN_LEN));
	let b = Math.min(d, Math.max(end, a + MIN_LEN));
	if (b - a < MIN_LEN) a = b - MIN_LEN;
	return [round(a), round(b)];
}

function setSpan(plan: EditPlan, ref: ItemRef, start: number, end: number): EditPlan {
	const [a, b] = clampSpan(plan, start, end);
	switch (ref.kind) {
		case 'graphic':
			return {...plan, graphics: plan.graphics.map((g) => (g.id === ref.id ? {...g, start: a, end: b} : g))};
		case 'zoom':
			return {...plan, zooms: plan.zooms.map((z, i) => (i === ref.index ? {...z, start: a, end: b} : z))};
		case 'layout':
			return {...plan, layout: plan.layout.map((l, i) => (i === ref.index ? {...l, start: a, end: b} : l))};
		case 'segment':
			return {...plan, segments: plan.segments.map((s, i) => (i === ref.index ? {...s, start: a, end: b} : s))};
		default:
			return plan;
	}
}

export function spanOf(plan: EditPlan, ref: ItemRef): [number, number] | null {
	switch (ref.kind) {
		case 'graphic': {
			const g = plan.graphics.find((x) => x.id === ref.id);
			return g ? [g.start, g.end] : null;
		}
		case 'zoom':
			return plan.zooms[ref.index] ? [plan.zooms[ref.index].start, plan.zooms[ref.index].end] : null;
		case 'layout':
			return plan.layout[ref.index] ? [plan.layout[ref.index].start, plan.layout[ref.index].end] : null;
		case 'segment':
			return plan.segments[ref.index] ? [plan.segments[ref.index].start, plan.segments[ref.index].end] : null;
		case 'caption': {
			const w = plan.transcript.words;
			return w[ref.first] && w[ref.last] ? [w[ref.first].start, w[ref.last].end] : null;
		}
	}
}

/**
 * Move a block so the piece you grabbed starts at reel second `to`. The source length is kept; the move is
 * worked out on the grabbed piece, so dragging the cold-open copy of something moves it sensibly too.
 */
export function moveItem(plan: EditPlan, ref: ItemRef, piece: Piece, to: number): EditPlan {
	const span = spanOf(plan, ref);
	if (!span || ref.kind === 'segment' || ref.kind === 'caption') return plan;
	const tl = timelineOf(plan);
	const delta = toSource(tl, to) - toSource(tl, piece.from);
	return setSpan(plan, ref, span[0] + delta, span[1] + delta);
}

/** Drag one edge of a block by `delta` reel seconds. Clip edges (Video track) trim the footage itself. */
export function trimItem(plan: EditPlan, ref: ItemRef, edge: 'start' | 'end', delta: number): EditPlan {
	const span = spanOf(plan, ref);
	if (!span || ref.kind === 'caption') return plan;
	const [a, b] = span;
	const d = delta * plan.style.pacing.speed; // reel seconds to source seconds
	if (edge === 'start') return setSpan(plan, ref, Math.min(a + d, b - MIN_LEN), b);
	return setSpan(plan, ref, a, Math.max(b + d, a + MIN_LEN));
}

export function removeItem(plan: EditPlan, ref: ItemRef): EditPlan {
	switch (ref.kind) {
		case 'graphic':
			return {...plan, graphics: plan.graphics.filter((g) => g.id !== ref.id)};
		case 'zoom':
			return {...plan, zooms: plan.zooms.filter((_, i) => i !== ref.index)};
		case 'layout':
			return {...plan, layout: plan.layout.filter((_, i) => i !== ref.index)};
		case 'segment': {
			const segs = plan.segments.length ? plan.segments : [{start: 0, end: plan.source.duration, reason: 'body' as const}];
			if (segs.length <= 1) return plan; // never cut the whole video
			return {...plan, segments: segs.filter((_, i) => i !== ref.index)};
		}
		case 'caption':
			return {...plan, transcript: {...plan.transcript, words: plan.transcript.words.filter((_, i) => i < ref.first || i > ref.last)}};
	}
}

/** Split the clip under reel second t into two, so one side can be deleted or trimmed. */
export function splitAt(plan: EditPlan, t: number): EditPlan {
	const tl = timelineOf(plan);
	const segs: Segment[] = plan.segments.length ? plan.segments : [{start: 0, end: plan.source.duration, reason: 'body'}];
	const frame = t * tl.fps;
	const i = tl.segments.findIndex((s) => frame > s.outFrom + 1 && frame < s.outFrom + s.frames - 1);
	if (i < 0) return plan;
	const cut = round(toSource(tl, t));
	const s = segs[i];
	return {...plan, segments: [...segs.slice(0, i), {...s, end: cut}, {...s, start: cut}, ...segs.slice(i + 1)]};
}

export function newGraphicId(plan: EditPlan, prefix: string): string {
	const used = new Set(plan.graphics.map((g) => g.id));
	let n = 1;
	while (used.has(`${prefix}${n}`)) n++;
	return `${prefix}${n}`;
}

export const NEW_PROPS: Partial<Record<GraphicType, Record<string, unknown>>> = {
	kinetic_text: {text: 'YOUR TEXT'},
	stat_card: {value: '10x', label: 'faster'},
	list_build: {title: '3 things', items: ['One', 'Two', 'Three']},
	lower_third: {title: 'Your name', subtitle: 'What you do'},
	emoji_burst: {emoji: '🔥'},
	progress_bar: {},
	orbit: {items: ['🔥', '💡', '🚀']},
	fly_out: {items: ['💰', '📈', '🔥']},
	particles: {kind: 'sparkles'},
};

export type Asset = {name: string; kind: 'image' | 'video'; label: string; duration?: number};

/** What can be dropped on the timeline from the bin. */
export type BinPayload =
	| {kind: 'graphic'; type: GraphicType}
	| {kind: 'asset'; asset: Asset}
	| {kind: 'restore'; id: string}
	| {kind: 'zoom'}
	| {kind: 'layout'; mode: LayoutMode};

/** Source span starting at reel second `at`, `len` seconds long (shortened at the jump after a hook). */
export function spanAt(plan: EditPlan, at: number, len: number): [number, number] {
	const tl = timelineOf(plan);
	const a = toSource(tl, at);
	let b = toSource(tl, Math.min(at + len, tl.durationInFrames / tl.fps));
	if (b <= a) {
		const seg = tl.segments.find((s) => a >= s.start && a < s.end);
		b = seg ? Math.min(seg.end, a + len) : a + len;
	}
	return clampSpan(plan, a, b);
}

/** Add what was dropped at reel second `at`. Returns the new plan and the new block's ref. */
export function dropOnTimeline(plan: EditPlan, payload: BinPayload, at: number, base?: EditPlan | null): {plan: EditPlan; ref: ItemRef | null} {
	switch (payload.kind) {
		case 'graphic': {
			const len = payload.type === 'progress_bar' ? reelDuration(plan) - at : payload.type === 'emoji_burst' ? 1.2 : payload.type === 'particles' ? 5 : 2.5;
			const [start, end] = spanAt(plan, at, len);
			const g: Graphic = {id: newGraphicId(plan, 'u'), type: payload.type, start, end, props: {...(NEW_PROPS[payload.type] ?? {})}, anchor: 'auto'};
			// Effects around the speaker need the speaker cut out, so adding one turns green-screen effects on.
			const style = isAroundType(payload.type) ? {...plan.style, depth: {...plan.style.depth, enabled: true}} : plan.style;
			return {plan: {...plan, style, graphics: [...plan.graphics, g]}, ref: {kind: 'graphic', id: g.id}};
		}
		case 'asset': {
			const a = payload.asset;
			const [start, end] = spanAt(plan, at, a.kind === 'video' ? Math.min(5, a.duration ?? 4) : 3);
			const props: Record<string, unknown> = {src: a.name, kind: a.kind, fit: 'cover', label: a.label};
			if (a.duration) props.duration = a.duration;
			const g: Graphic = {id: newGraphicId(plan, 'm'), type: 'media', start, end, props, anchor: 'auto'};
			return {plan: {...plan, graphics: [...plan.graphics, g]}, ref: {kind: 'graphic', id: g.id}};
		}
		case 'restore': {
			const old = base?.graphics.find((g) => g.id === payload.id);
			if (!old || plan.graphics.some((g) => g.id === old.id)) return {plan, ref: null};
			const [start, end] = spanAt(plan, at, old.end - old.start);
			return {plan: {...plan, graphics: [...plan.graphics, {...old, start, end}]}, ref: {kind: 'graphic', id: old.id}};
		}
		case 'zoom': {
			const [start, end] = spanAt(plan, at, 1.5);
			const zooms = [...plan.zooms, {start, end, scale: plan.style.camera.zoom_scale, ease: 'ease_in_out' as const}];
			return {plan: {...plan, zooms}, ref: {kind: 'zoom', index: zooms.length - 1}};
		}
		case 'layout': {
			const [start, end] = spanAt(plan, at, 4);
			const next = setLayout(plan, start, end, payload.mode);
			const index = next.layout.findIndex((l) => l.start === start && l.mode === payload.mode);
			return {plan: next, ref: index >= 0 ? {kind: 'layout', index} : null};
		}
	}
}

/** Put a removed block back where it was. */
export function restoreGraphic(plan: EditPlan, base: EditPlan, id: string): EditPlan {
	const old = base.graphics.find((g) => g.id === id);
	if (!old || plan.graphics.some((g) => g.id === id)) return plan;
	return {...plan, graphics: [...plan.graphics, old]};
}

/** Blocks the pipeline made that are no longer on the timeline, so they can be dragged back. */
export function removedGraphics(plan: EditPlan, base: EditPlan | null | undefined): Graphic[] {
	if (!base) return [];
	const ids = new Set(plan.graphics.map((g) => g.id));
	return base.graphics.filter((g) => !ids.has(g.id));
}

export function duplicateItem(plan: EditPlan, ref: ItemRef): {plan: EditPlan; ref: ItemRef | null} {
	const span = spanOf(plan, ref);
	if (!span) return {plan, ref: null};
	const len = span[1] - span[0];
	const [a, b] = clampSpan(plan, span[1], span[1] + len);
	if (ref.kind === 'graphic') {
		const g = plan.graphics.find((x) => x.id === ref.id)!;
		const copy = {...g, id: newGraphicId(plan, g.type === 'media' ? 'm' : 'u'), start: a, end: b, props: {...g.props}};
		return {plan: {...plan, graphics: [...plan.graphics, copy]}, ref: {kind: 'graphic', id: copy.id}};
	}
	if (ref.kind === 'zoom') {
		const zooms = [...plan.zooms, {...plan.zooms[ref.index], start: a, end: b}];
		return {plan: {...plan, zooms}, ref: {kind: 'zoom', index: zooms.length - 1}};
	}
	return {plan, ref: null};
}

export function updateGraphic(plan: EditPlan, id: string, patch: Partial<Graphic>): EditPlan {
	return {...plan, graphics: plan.graphics.map((g) => (g.id === id ? {...g, ...patch, props: {...g.props, ...(patch.props ?? {})}} : g))};
}

/** Make source [start, end) use `mode`, trimming or splitting the layout spans it overlaps. */
export function setLayout(plan: EditPlan, start: number, end: number, mode: LayoutMode): EditPlan {
	const out = [];
	for (const l of plan.layout) {
		if (l.end <= start || l.start >= end) {
			out.push(l);
			continue;
		}
		if (l.start < start) out.push({...l, end: start});
		if (l.end > end) out.push({...l, start: end});
	}
	if (mode !== 'speaker') out.push({start, end, mode});
	return {...plan, layout: out.sort((a, b) => a.start - b.start)};
}

/** How a visual block is shown: split screen (speaker below) or full screen, by the layout under it. */
export function showAs(plan: EditPlan, id: string, mode: 'split' | 'visual'): EditPlan {
	const g = plan.graphics.find((x) => x.id === id);
	return g ? setLayout(plan, g.start, g.end, mode) : plan;
}

export function modeUnder(plan: EditPlan, g: Graphic): LayoutMode {
	const mid = (g.start + g.end) / 2;
	const l = plan.layout.find((s) => mid >= s.start && mid < s.end);
	return l && l.mode !== 'speaker' ? l.mode : 'split';
}

/** Reel times worth snapping to: word starts, block edges and the playhead. */
export function snapPoints(plan: EditPlan, items: Item[], skipKey?: string): number[] {
	const tl = timelineOf(plan);
	const pts: number[] = [0, tl.durationInFrames / tl.fps];
	for (const w of plan.transcript.words) for (const f of sourceToFrames(tl, w.start)) pts.push(f / tl.fps);
	for (const it of items) if (it.key !== skipKey && it.track !== 'captions') for (const p of it.pieces) pts.push(p.from, p.to);
	return pts.sort((a, b) => a - b);
}

export function snap(t: number, points: number[], tolerance: number): number {
	let best = t;
	let bestD = tolerance;
	for (const p of points) {
		const d = Math.abs(p - t);
		if (d < bestD) {
			best = p;
			bestD = d;
		}
	}
	return best;
}

export const fmtTime = (t: number): string => {
	const m = Math.floor(t / 60);
	const s = t - m * 60;
	return `${m}:${s.toFixed(1).padStart(4, '0')}`;
};
