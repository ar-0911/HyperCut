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
] as const;
export type GraphicType = (typeof GRAPHIC_TYPES)[number];
export type Anchor = 'auto' | 'top' | 'center' | 'bottom';

export type Graphic = Span & {
	id: string;
	type: GraphicType;
	props: Record<string, unknown>;
	anchor: Anchor;
};
export type Zoom = Span & {scale: number; ease: 'linear' | 'ease_in_out' | 'snap'};
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
};
export type GraphicsStyle = {
	density: 'minimal' | 'balanced' | 'heavy';
	theme: 'clean' | 'bold' | 'playful' | 'cinematic';
	accent_color: string;
};
export type Style = {
	name: string;
	caption: CaptionStyle;
	graphics: GraphicsStyle;
	pacing: {remove_fillers: boolean; max_silence: number};
	camera: {zoom_frequency: 'none' | 'low' | 'medium' | 'high'; zoom_scale: number};
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
	reframe: {keys: ReframeKey[]};
	style: Style;
};

export type CompositionProps = {plan: EditPlan; videoSrc: string};

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
	graphics: {density: 'balanced', theme: 'bold', accent_color: '#FFE600'},
	pacing: {remove_fillers: true, max_silence: 0.35},
	camera: {zoom_frequency: 'medium', zoom_scale: 1.15},
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
		graphics: (r.graphics ?? []).map((g: object) => ({props: {}, anchor: 'auto' as const, ...g})),
		zooms: (r.zooms ?? []).map((z: object) => ({scale: 1.15, ease: 'ease_in_out' as const, ...z})),
		reframe: {keys: [], ...(r.reframe ?? {})},
		style: {
			...DEFAULT_STYLE,
			...style,
			caption: {...DEFAULT_CAPTION, ...(style.caption ?? {})},
			graphics: {...DEFAULT_STYLE.graphics, ...(style.graphics ?? {})},
			pacing: {...DEFAULT_STYLE.pacing, ...(style.pacing ?? {})},
			camera: {...DEFAULT_STYLE.camera, ...(style.camera ?? {})},
		},
	};
}
