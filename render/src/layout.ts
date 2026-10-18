// Pure geometry: reframe interpolation, crop rectangle, zoom curve, graphic placement, layout modes.

import type {Anchor, BackgroundSpan, EditPlan, Graphic, GraphicType, LayoutMode, LayoutSpan, ReframeKey, Zoom} from './plan';

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/**
 * Reframe at source time t: linear between keys, held at the ends, 0.5/0.5 with no keys. cx is the
 * horizontal crop center, cy the face's height in the source frame.
 */
export function reframeAt(keys: ReframeKey[], t: number): {cx: number; cy: number} {
	if (!keys.length) return {cx: 0.5, cy: 0.5};
	const ks = [...keys].sort((a, b) => a.t - b.t);
	if (t <= ks[0].t) return {cx: ks[0].cx, cy: ks[0].cy};
	const last = ks[ks.length - 1];
	if (t >= last.t) return {cx: last.cx, cy: last.cy};
	let i = 0;
	while (ks[i + 1].t < t) i++;
	const a = ks[i];
	const b = ks[i + 1];
	const k = (t - a.t) / (b.t - a.t);
	return {cx: a.cx + (b.cx - a.cx) * k, cy: a.cy + (b.cy - a.cy) * k};
}

export type CropRect = {
	/** Size of the scaled source frame in output pixels. */
	width: number;
	height: number;
	/** Offset of its top-left corner inside the output frame (<= 0). */
	left: number;
	top: number;
};

/** Scale the source to cover the output, then slide so (cx, cy) is as central as the edges allow. */
export function cropRect(
	src: {width: number; height: number},
	out: {width: number; height: number},
	cx: number,
	cy: number,
): CropRect {
	const scale = Math.max(out.width / src.width, out.height / src.height);
	const width = src.width * scale;
	const height = src.height * scale;
	return {
		width,
		height,
		left: -clamp(cx * width - out.width / 2, 0, width - out.width),
		top: -clamp(cy * height - out.height / 2, 0, height - out.height),
	};
}

/** Where a source point (nx, ny in 0..1) lands in the output frame for a given crop. */
export function pointInOutput(rect: CropRect, nx: number, ny: number): {x: number; y: number} {
	return {x: rect.left + nx * rect.width, y: rect.top + ny * rect.height};
}

const smooth = (k: number) => k * k * (3 - 2 * k);

/** Zoom factor at source time t. Overlapping zooms: the strongest wins. 1 outside any zoom. */
export function zoomAt(zooms: Zoom[], t: number): number {
	let best = 1;
	for (const z of zooms) {
		if (t < z.start || t >= z.end) continue;
		const dur = z.end - z.start;
		let k: number;
		if (z.ease === 'snap') {
			k = clamp((t - z.start) / 0.08, 0, 1); // ~2 frames: reads as a cut-in
		} else if (z.ease === 'linear') {
			k = (t - z.start) / dur;
		} else {
			const ramp = Math.min(0.3, dur / 2);
			k = smooth(clamp(Math.min((t - z.start) / ramp, (z.end - t) / ramp), 0, 1));
		}
		best = Math.max(best, 1 + (z.scale - 1) * k);
	}
	return best;
}

// ---- graphic placement ----------------------------------------------------------------------

export type Band = 'top' | 'center' | 'bottom';

/** Vertical center of each band as a fraction of output height. The bottom band sits above captions. */
export const BAND_Y: Record<Band, number> = {top: 0.14, center: 0.5, bottom: 0.7};
/** Where captions sit, same units, so graphics avoid them as well. */
export const CAPTION_Y: Record<'top' | 'middle' | 'bottom', number> = {top: 0.14, middle: 0.5, bottom: 0.82};

/** Half-height (fraction of output height) the face plus hair and shoulders may occupy. */
export const FACE_HALF = 0.19;
/** Half-height of a typical graphic block. */
export const GRAPHIC_HALF = 0.09;

const BANDS: Band[] = ['top', 'bottom', 'center'];

/**
 * Pick the band for a graphic. The anchor is honored unless it would overlap the face or the
 * captions; then the free band furthest from the face wins. faceY is the face center as a fraction
 * of output height (0.5 when unknown).
 */
export function placeGraphic(
	anchor: Anchor,
	faceY: number,
	captionPos: 'top' | 'middle' | 'bottom',
): Band {
	const clear = (b: Band) =>
		Math.abs(BAND_Y[b] - faceY) >= FACE_HALF + GRAPHIC_HALF &&
		Math.abs(BAND_Y[b] - CAPTION_Y[captionPos]) >= GRAPHIC_HALF * 2;
	if (anchor !== 'auto' && clear(anchor)) return anchor;
	const free = BANDS.filter(clear);
	const pool = free.length ? free : BANDS;
	return pool.reduce((best, b) =>
		Math.abs(BAND_Y[b] - faceY) > Math.abs(BAND_Y[best] - faceY) ? b : best,
	);
}

// ---- layout modes ---------------------------------------------------------------------------

/** Split layout: the speaker panel is the bottom (1 - SPLIT) of the frame, visuals the top SPLIT. */
export const SPLIT = 0.5;
/** Seconds the speaker panel takes to slide from full frame into the bottom half. */
export const SPLIT_IN = 0.3;
/** Seconds a full-frame visual takes to fade/scale in. */
export const VISUAL_IN = 0.25;
/** Vertical area (fractions of output height) the split layout's top panel lays graphics out in. */
export const SPLIT_AREA = {top: 0.03, bottom: 0.44};
/** Same for a full-frame visual; captions sit below it. */
export const VISUAL_AREA = {top: 0.06, bottom: 0.74};

/** Graphic types that can carry a split top panel or a full-frame visual. */
export const VISUAL_TYPES: readonly GraphicType[] = ['illustration', 'kinetic_text', 'stat_card', 'list_build', 'media'];
export const isVisualType = (type: GraphicType) => VISUAL_TYPES.includes(type);
/** Effects around the cut-out speaker (ADR 0610): drawn by Around.tsx, behind and in front of the speaker. */
export const AROUND_TYPES: readonly GraphicType[] = ['orbit', 'fly_out', 'particles'];
export const isAroundType = (type: GraphicType) => AROUND_TYPES.includes(type);
/** Stage graphics (ADR 0611): drawn by Stage.tsx behind the cut-out speaker. */
export const STAGE_TYPES: readonly GraphicType[] = ['card_stack', 'scene', 'chart'];
export const isStageType = (type: GraphicType) => STAGE_TYPES.includes(type);
/** How much a scene or chart shrinks the speaker (about the bottom of the frame under the face), so it shows. */
export const PULL_BACK = 0.26;
/** Seconds the speaker takes to pull back and to come forward again. */
export const PULL_IN = 0.45;

const EPS = 1e-3;

/**
 * Layout mode at source time t and seconds since it started (Infinity outside every span).
 * Back-to-back spans of the same mode count as one, so they do not re-animate at the seam.
 */
export function layoutAt(spans: LayoutSpan[], t: number): {mode: LayoutMode; enter: number} {
	const ks = [...spans].sort((a, b) => a.start - b.start);
	const i = ks.findIndex((s) => t >= s.start && t < s.end);
	if (i < 0) return {mode: 'speaker', enter: Infinity};
	const {mode} = ks[i];
	let start = ks[i].start;
	for (let j = i - 1; j >= 0; j--) {
		const p = ks[j];
		if (p.mode === mode && p.end >= start - EPS && p.start < start) start = p.start;
	}
	return {mode, enter: t - start};
}

/**
 * The mode actually drawn at t: the layout mode, except that a split or visual span with no visual
 * graphic on screen falls back to speaker (never an empty panel), and a visual graphic during a speaker
 * span opens the split panel (text cards never sit on the face). `enter` counts from when the run of
 * visual graphics inside the span began, so a visual arriving mid-span still animates in.
 */
export function modeAt(spans: LayoutSpan[], graphics: Graphic[], t: number): {mode: LayoutMode; enter: number} {
	const l = layoutAt(spans, t);
	// Graphics behind the speaker never open a panel: they are drawn behind the speaker, or (without a
	// cut-out) in front of them off the face.
	const vis = graphics.filter((g) => isVisualType(g.type) && g.layer !== 'behind');
	const active = vis.filter((g) => t >= g.start && t < g.end);
	if (!active.length) return {mode: 'speaker', enter: Infinity};
	// A visual during a speaker span opens the split panel rather than covering the speaker's face.
	const mode: LayoutMode = l.mode === 'speaker' ? 'split' : l.mode;
	// Walk back through overlapping / touching visuals to the start of this run of coverage.
	let start = Math.min(...active.map((g) => g.start));
	for (let moved = true; moved; ) {
		moved = false;
		for (const g of vis) {
			if (g.start < start && g.end >= start - EPS) {
				start = g.start;
				moved = true;
			}
		}
	}
	const spanStart = l.mode === 'speaker' ? -Infinity : t - l.enter;
	return {mode, enter: t - Math.max(start, spanStart)};
}

/** Extra zoom on the speaker in split mode: half-size framing of a wide shot leaves the face small. */
export const SPLIT_PUNCH = 1.35;

const easeInOut = (k: number) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);

/** The speaker panel (output pixels): full frame, or sliding into the bottom part in split mode. */
export function panelAt(mode: LayoutMode, enter: number, height: number): {top: number; height: number} {
	if (mode !== 'split') return {top: 0, height};
	const k = easeInOut(clamp(enter / SPLIT_IN, 0, 1));
	const top = SPLIT * height * k;
	return {top, height: height - top};
}

/** Caption center (fraction of output height): style position, the split seam, or bottom over a visual. */
export function captionY(mode: LayoutMode, position: 'top' | 'middle' | 'bottom'): number {
	if (mode === 'split') return SPLIT;
	if (mode === 'visual') return CAPTION_Y.bottom;
	return CAPTION_Y[position];
}

export type Scene = {
	mode: LayoutMode;
	enter: number;
	/** Speaker panel in output pixels. */
	panel: {top: number; height: number};
	/** Crop of the source inside the panel (panel-local pixels). */
	rect: CropRect;
	zoom: number;
	/** Zoom origin: the face, panel-local pixels. */
	origin: {x: number; y: number};
	/** The face in output pixels (a zoom about it does not move it). */
	face: {x: number; y: number};
	/** Face height as a fraction of output height for graphic placement (0.4 without a face track). */
	faceY: number;
	captionY: number;
};

/** Everything about the frame's arrangement at source time t, shared by the video and overlay layers. */
export function sceneAt(plan: EditPlan, t: number): Scene {
	const {width, height} = plan.output;
	const {mode, enter} = modeAt(plan.layout, plan.graphics, t);
	const panel = panelAt(mode, enter, height);
	const {cx, cy} = reframeAt(plan.reframe.keys, t);
	const rect = cropRect(plan.source, {width, height: panel.height}, cx, cy);
	const p = pointInOutput(rect, cx, cy);
	// Scaling (>= 1) about a point inside the panel keeps the panel covered.
	const origin = {x: clamp(p.x, 0, width), y: clamp(p.y, 0, panel.height)};
	const face = {x: origin.x, y: panel.top + origin.y};
	return {
		mode,
		enter,
		panel,
		rect,
		// In split mode the speaker is drawn at half size, so punch in on the face as the panel slides.
		zoom: zoomAt(plan.zooms, t) * (1 + (SPLIT_PUNCH - 1) * (panel.top / (SPLIT * height))),
		origin,
		face,
		faceY: plan.reframe.keys.length ? face.y / height : 0.4,
		// While the speaker panel slides down, the caption line travels with the seam.
		captionY:
			mode === 'split'
				? captionY('speaker', plan.style.caption.position) +
					(SPLIT - captionY('speaker', plan.style.caption.position)) * (panel.top / (SPLIT * height))
				: captionY(mode, plan.style.caption.position),
	};
}

/** What is behind the cut-out speaker at source time t: the span covering t, else the style default. */
export function backgroundAt(plan: EditPlan, t: number): BackgroundSpan {
	const span = plan.backgrounds.find((b) => t >= b.start && t < b.end);
	return span ?? {start: 0, end: plan.source.duration, kind: plan.style.depth.background, parallax: 0};
}

/**
 * Green-screen state at source time t (ADR 0901). Null when the effects are off: not asked for, no cut-out
 * video, or a full-frame visual covering the speaker. `behind` lists the graphics drawn behind the
 * speaker (only where the speaker fills the frame); `cutout` says whether the cut-out speaker must be
 * drawn on top this frame (a replaced or treated background, or something behind them).
 */
export function depthAt(
	plan: EditPlan,
	t: number,
	mode: LayoutMode,
	hasMatte: boolean,
): {background: BackgroundSpan; behind: Graphic[]; around: Graphic[]; stage: Graphic[]; pull: number; shift: number; cutout: boolean} | null {
	if (!hasMatte || !plan.style.depth.enabled || mode === 'visual') return null;
	const background = backgroundAt(plan, t);
	const speaker = mode === 'speaker';
	const active = (g: Graphic) => t >= g.start && t < g.end;
	const behind = speaker ? plan.graphics.filter((g) => g.layer === 'behind' && !isAroundType(g.type) && !isStageType(g.type) && active(g)) : [];
	const around = speaker ? aroundAt(plan, t) : [];
	const stage = speaker ? plan.graphics.filter((g) => isStageType(g.type) && active(g)) : [];
	const pull = speaker ? pullAt(plan, t) : 0;
	const shift = speaker && pull > 0 ? shiftAt(plan, t, sceneAt(plan, t).face.x) : 0;
	const cutout = background.kind !== 'original' || behind.length > 0 || around.length > 0 || stage.length > 0 || pull > 0;
	return {background, behind, around, stage, pull, shift, cutout};
}

/** 0..1 eased presence of a stage graphic at t: in over PULL_IN, out over PULL_IN. */
const presence = (g: Graphic, t: number) => {
	if (t < g.start || t >= g.end) return 0;
	const x = Math.min(1, (t - g.start) / PULL_IN, (g.end - t) / PULL_IN);
	return x * x * (3 - 2 * x);
};

/** 0..1: how far the speaker is pulled back for a stage graphic at source time t, eased in and out. */
export function pullAt(plan: EditPlan, t: number): number {
	return Math.max(0, ...plan.graphics.filter((g) => isStageType(g.type)).map((g) => presence(g, t)));
}

/** The side of the frame cards go to: away from the face, the right when the face is centred. */
export const freeSide = (faceX: number, width: number): 'left' | 'right' => (faceX > width / 2 ? 'left' : 'right');

/** Where the face goes while cards are up: a third of the way in from the side away from the cards. */
export const CARD_FACE_X = 0.34;

/**
 * Pixels the speaker moves sideways at t: while cards are up, away from them so they have room (the
 * reframe keeps the face near the centre, so there is rarely a free side otherwise).
 */
export function shiftAt(plan: EditPlan, t: number, faceX: number): number {
	const {width} = plan.output;
	const cards = plan.graphics.find((g) => g.type === 'card_stack' && t >= g.start && t < g.end);
	if (!cards) return 0;
	const target = freeSide(faceX, width) === 'left' ? (1 - CARD_FACE_X) * width : CARD_FACE_X * width;
	return (target - faceX) * presence(cards, t);
}

/** Effects around the speaker active at source time t (drawn in speaker stretches only). */
export const aroundAt = (plan: EditPlan, t: number): Graphic[] => plan.graphics.filter((g) => isAroundType(g.type) && t >= g.start && t < g.end);
