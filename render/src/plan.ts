// Hand-written mirror of schema/edit_plan.schema.json (hypercut/plan.py is the source of truth).
// All times are seconds on the SOURCE timeline.

export type Span = {start: number; end: number};

export type Source = {path: string; width: number; height: number; fps: number; duration: number};
export type Output = {width: number; height: number; fps: number};
export type Word = Span & {text: string; speaker?: string | null; confidence?: number | null};
export type Segment = Span & {reason: 'hook' | 'body'};

export const GRAPHIC_TYPES = [
	'kinetic_text',
	'stat_card',
	'emoji_burst',
	'list_build',
	'lower_third',
	'progress_bar',
	'illustration',
	// Footage or a picture the user imported (B-roll). props: {src, kind: 'image' | 'video', fit, trim_start, duration, label}
	'media',
	// Effects around the cut-out speaker (ADR 0610), passing behind and in front of them, never over the face.
	// orbit / fly_out props: {items: string[]} (emoji or 1-2 words); particles props: {kind: sparkles|bokeh|confetti|embers}
	'orbit',
	'fly_out',
	'particles',
	// Stage graphics behind the cut-out speaker (ADR 0611). card_stack props: {cards: [{title, brief, viewBox,
	// defs, layers}]}; scene props: {title, brief, viewBox, defs, layers}; chart props: {headline, kind: line|bars,
	// values: number[], labels: string[], unit}
	'card_stack',
	'scene',
	'chart',
	// A full-screen 3D motion graphic for a few seconds (ADR 0612). props: {title, idea, scene: {objects, camera, look}}
	'motion',
] as const;
export type GraphicType = (typeof GRAPHIC_TYPES)[number];
export type Anchor = 'auto' | 'top' | 'center' | 'bottom';

/** front: over the speaker. behind: between the background and the cut-out speaker (needs a matte). */
export type GraphicLayer = 'front' | 'behind';
export type Graphic = Span & {
	id: string;
	type: GraphicType;
	props: Record<string, unknown>;
	anchor: Anchor;
	layer?: GraphicLayer;
};
export type BackgroundKind = 'original' | 'blur' | 'dim' | 'color' | 'gradient' | 'media';
/** What is behind the cut-out speaker for a stretch of source time (green-screen effects, ADR 0901). */
export type BackgroundSpan = Span & {kind: BackgroundKind; color?: string | null; src?: string | null; parallax: number};
/** Green-screen effects: off unless the user asked for them. */
export type Depth = {enabled: boolean; background: BackgroundKind; behind_titles: boolean; around: boolean};
export type LayoutMode = 'speaker' | 'split' | 'visual';
/** How the frame is arranged for a stretch of source time. Outside every span: speaker. */
export type LayoutSpan = Span & {mode: LayoutMode};
export type CutKind = 'drop' | 'whip' | 'zoom' | 'push';
/** An animated transition into the footage that starts at source time `at`: the frame before it is held and moved away. */
export type CutTransition = {at: number; kind: CutKind; length: number};
export type Zoom = Span & {scale: number; ease: 'linear' | 'ease_in_out' | 'snap'};
/** cx: horizontal crop center; cy: the face's height in the source frame (0.5 in older plans). */
export type ReframeKey = {t: number; cx: number; cy: number};

export type CaptionAnimation = 'karaoke' | 'pop' | 'typewriter' | 'bounce';
export type CaptionStyle = {
	font: string;
	weight: number;
	size: number;
	color: string;
	highlight_color: string;
	stroke_color: string;
	stroke_width: number;
	uppercase: boolean;
	position: 'top' | 'middle' | 'bottom';
	words_per_line: number;
	animation: CaptionAnimation;
	/** A rounded box behind each line (a CSS colour) instead of an outline; null/undefined: none. */
	box?: string | null;
};
export type GraphicsStyle = {
	density: 'minimal' | 'balanced' | 'heavy';
	theme: 'clean' | 'bold' | 'playful' | 'cinematic';
	accent_color: string;
	/** Tags and chart details (ADR 0611); default the accent. */
	secondary_color?: string | null;
	/** Dark panels and card labels. */
	panel_color?: string;
};
export type Pacing = {remove_fillers: boolean; max_silence: number; keep_pause: number; speed: number};
export type TransitionStyle = 'hard' | 'smooth' | 'zoom';
/** How kept pieces meet (hard cut, crossfade, alternating punch-in) and the fade in/out of the reel. */
export type Transitions = {style: TransitionStyle; length: number; fade_in: number; fade_out: number};
export type Style = {
	name: string;
	caption: CaptionStyle;
	graphics: GraphicsStyle;
	pacing: Pacing;
	camera: {zoom_frequency: 'none' | 'low' | 'medium' | 'high'; zoom_scale: number};
	transitions: Transitions;
	depth: Depth;
};

export type EditPlan = {
	version: 1;
	source: Source;
	output: Output;
	transcript: {language: string; words: Word[]};
	hook: {strategy: 'cold_open' | 'trim'; chosen: number; candidates: (Span & {text: string; score: number; why: string})[]};
	segments: Segment[];
	graphics: Graphic[];
	zooms: Zoom[];
	/** Empty: speaker full frame throughout. */
	layout: LayoutSpan[];
	/** Only used with style.depth.enabled and a matte. */
	backgrounds: BackgroundSpan[];
	reframe: {keys: ReframeKey[]; shots: number[]};
	style: Style;
	/** Animated transitions (ADR 0613); elsewhere footage meets by style.transitions. */
	cuts: CutTransition[];
};

/**
 * videoSrc: the speaker video. assetBase: where imported media files are fetched from (a URL prefix in
 * the browser preview); omitted in the final render, where they sit next to the video as static files.
 * matteSrc: the speaker cut-out video (transparent outside the speaker) for green-screen effects; without
 * it those effects are skipped and graphics meant to go behind the speaker are drawn in front, off the face.
 */
export type CompositionProps = {plan: EditPlan; videoSrc: string; assetBase?: string; matteSrc?: string};

export const DEFAULT_CAPTION: CaptionStyle = {
	font: 'Montserrat',
	weight: 800,
	size: 72,
	color: '#FFFFFF',
	highlight_color: '#FFE600',
	stroke_color: '#000000',
	stroke_width: 6,
	uppercase: true,
	position: 'bottom',
	words_per_line: 3,
	animation: 'pop',
};

export const DEFAULT_STYLE: Style = {
	name: 'bold_creator',
	caption: DEFAULT_CAPTION,
	graphics: {density: 'balanced', theme: 'bold', accent_color: '#FFE600', secondary_color: null, panel_color: '#0E1330'},
	pacing: {remove_fillers: true, max_silence: 0.35, keep_pause: 0.15, speed: 1},
	camera: {zoom_frequency: 'medium', zoom_scale: 1.15},
	transitions: {style: 'smooth', length: 0.2, fade_in: 0, fade_out: 0.8},
	depth: {enabled: false, background: 'original', behind_titles: true, around: true},
};

/**
 * Fill in everything the Python side would default, so a hand-written or partial plan renders too.
 * Throws on a plan that cannot render at all (no source, wrong version).
 */
export function normalizePlan(raw: unknown): EditPlan {
	// Untyped on purpose: the input is whatever JSON came off disk, possibly with defaults omitted.
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	const r = raw as any;
	if (!r || typeof r !== 'object') throw new Error('plan must be a JSON object');
	if (r.version !== undefined && r.version !== 1) throw new Error(`unsupported plan version ${r.version}`);
	const s = r.source;
	if (!s || !(s.width > 0) || !(s.height > 0) || !(s.fps > 0) || !(s.duration > 0)) {
		throw new Error('plan.source needs positive width, height, fps and duration');
	}
	const style = r.style ?? ({} as Partial<Style>);
	return {
		version: 1,
		source: s,
		output: {width: 1080, height: 1920, fps: 30, ...(r.output ?? {})},
		transcript: {language: 'en', words: [], ...(r.transcript ?? {})},
		hook: {strategy: 'cold_open', chosen: 0, candidates: [], ...(r.hook ?? {})},
		segments: (r.segments ?? []).map((g: object) => ({reason: 'body' as const, ...g})),
		graphics: (r.graphics ?? []).map((g: object) => ({props: {}, anchor: 'auto' as const, layer: 'front' as const, ...g})),
		zooms: (r.zooms ?? []).map((z: object) => ({scale: 1.15, ease: 'ease_in_out' as const, ...z})),
		layout: (r.layout ?? []).map((l: object) => ({mode: 'speaker' as const, ...l})),
		backgrounds: (r.backgrounds ?? []).map((b: object) => ({kind: 'blur' as const, parallax: 0, ...b})),
		reframe: {keys: [], shots: [], ...(r.reframe ?? {})},
		cuts: (r.cuts ?? []).map((c: object) => ({kind: 'drop' as const, length: 0.5, ...c})),
		style: {
			...DEFAULT_STYLE,
			...style,
			caption: {...DEFAULT_CAPTION, ...(style.caption ?? {})},
			graphics: {...DEFAULT_STYLE.graphics, ...(style.graphics ?? {})},
			pacing: {...DEFAULT_STYLE.pacing, ...(style.pacing ?? {})},
			camera: {...DEFAULT_STYLE.camera, ...(style.camera ?? {})},
			transitions: {...DEFAULT_STYLE.transitions, ...(style.transitions ?? {})},
			depth: {...DEFAULT_STYLE.depth, ...(style.depth ?? {})},
		},
	};
}
