import React from 'react';
import {BAND_Y, CAPTION_Y, placeGraphic, SPLIT_AREA, VISUAL_AREA} from './layout';
import type {Graphic, GraphicsStyle, LayoutMode} from './plan';
import {themeTokens, type Theme} from './theme';

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const easeOutBack = (k: number) => {
	const c1 = 1.70158;
	return 1 + (c1 + 1) * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2);
};
const str = (v: unknown, fallback = '') => (v === undefined || v === null ? fallback : String(v));

type TemplateProps = {
	graphic: Graphic;
	/** Seconds since the graphic started / seconds left. */
	elapsed: number;
	remaining: number;
	/** 0..1 through the graphic's span. */
	progress: number;
	theme: Theme;
	/** Output frame size. */
	width: number;
	height: number;
	/** The area the graphic is laid out in (a top panel, most of the frame, or a card). */
	boxWidth: number;
	boxHeight: number;
	mode: LayoutMode;
};

/** In: pop with overshoot over 0.3 s. Out: fade over the last 0.2 s. */
const enter = (elapsed: number, delay = 0, dur = 0.3) => easeOutBack(clamp01((elapsed - delay) / dur));
const fadeOut = (remaining: number) => clamp01(remaining / 0.2);

const KineticText: React.FC<TemplateProps> = ({graphic, elapsed, remaining, theme, width}) => {
	const words = str(graphic.props.text, 'Wow').split(/\s+/).filter(Boolean);
	return (
		<div style={{display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: '0 24px', maxWidth: width - 140, opacity: fadeOut(remaining)}}>
			{words.map((w, i) => {
				const k = enter(elapsed, i * 0.12);
				return (
					<span
						key={i}
						style={{
							display: 'inline-block',
							fontFamily: theme.fontFamily,
							fontWeight: 900,
							fontSize: 120,
							lineHeight: 1.05,
							color: i % 2 ? theme.accent : theme.text,
							textTransform: theme.uppercase ? 'uppercase' : 'none',
							WebkitTextStroke: '10px #000',
							paintOrder: 'stroke fill',
							opacity: clamp01(k * 2),
							transform: `translateY(${(1 - k) * 60}px) scale(${0.6 + 0.4 * k}) rotate(${(1 - k) * (i % 2 ? 6 : -6)}deg)`,
						}}
					>
						{w}
					</span>
				);
			})}
		</div>
	);
};

const StatCard: React.FC<TemplateProps> = ({graphic, elapsed, remaining, theme}) => {
	const k = enter(elapsed);
	const value = str(graphic.props.value, '100%');
	// Count up when the value is numeric, so the number feels like it lands.
	const m = value.match(/^([^\d-]*)(-?[\d,.]+)(.*)$/);
	let shown = value;
	if (m) {
		const target = parseFloat(m[2].replace(/,/g, ''));
		if (Number.isFinite(target)) {
			const decimals = (m[2].split('.')[1] ?? '').length;
			const v = target * clamp01(elapsed / 0.6);
			shown = `${m[1]}${v.toFixed(decimals)}${m[3]}`;
		}
	}
	return (
		<div
			style={{
				fontFamily: theme.fontFamily,
				background: theme.panel,
				color: theme.panelText,
				border: theme.border,
				borderRadius: theme.radius,
				boxShadow: theme.shadow,
				padding: '36px 64px',
				textAlign: 'center',
				opacity: fadeOut(remaining) * clamp01(k * 2),
				transform: `scale(${0.5 + 0.5 * k})`,
			}}
		>
			<div style={{fontSize: 190, fontWeight: 900, lineHeight: 1, color: theme.accent === theme.panel ? theme.panelText : theme.accent}}>{shown}</div>
			<div style={{fontSize: 52, fontWeight: theme.fontWeight, marginTop: 12, textTransform: theme.uppercase ? 'uppercase' : 'none'}}>
				{str(graphic.props.label)}
			</div>
		</div>
	);
};

/** Furthest an emoji center may travel vertically, as a fraction of output height: the burst stays in its band. */
export const EMOJI_REACH_Y = 0.12;

const EmojiBurst: React.FC<TemplateProps> = ({graphic, elapsed, remaining, width, height, mode}) => {
	// Next to a visual the burst is an accent, not the subject.
	const shrink = mode === 'speaker' ? 1 : 0.6;
	const emoji = str(graphic.props.emoji, '🔥');
	const count = Math.min(14, Math.max(3, Number(graphic.props.count ?? 8)));
	const limit = EMOJI_REACH_Y * height * shrink;
	return (
		<div style={{position: 'relative', width: 0, height: 0, opacity: fadeOut(remaining)}}>
			{Array.from({length: count}, (_, i) => {
				// Deterministic fan-out: no Math.random, so every render of a frame is identical.
				const angle = (i / count) * Math.PI * 2 + 0.3 * (i % 2);
				const reach = (260 + (i % 3) * 90) * clamp01(elapsed / 0.5) * shrink;
				// Over the speaker: two low clusters at the frame's sides; next to a visual: a fan.
				const side = i % 2 ? 1 : -1;
				const x = mode === 'speaker' ? side * (width * 0.36 + Math.cos(angle) * reach * 0.25) : Math.cos(angle) * reach;
				const rise = mode === 'speaker' ? 0.2 : 0.5;
				// Clamped so the burst never climbs onto the face.
				const y = Math.max(-limit * rise, Math.min(limit * rise, Math.sin(angle) * reach * rise - elapsed * 40));
				const size = (120 + (i % 3) * 36) * shrink;
				return (
					<span
						key={i}
						style={{
							position: 'absolute',
							left: x,
							top: y,
							fontSize: size,
							fontFamily: '"Noto Color Emoji", "Apple Color Emoji", "Segoe UI Emoji", sans-serif',
							transform: `translate(-50%, -50%) scale(${enter(elapsed, (i % 4) * 0.04)}) rotate(${(i % 2 ? 1 : -1) * 15 * clamp01(elapsed / 0.5)}deg)`,
						}}
					>
						{emoji}
					</span>
				);
			})}
		</div>
	);
};

const ListBuild: React.FC<TemplateProps> = ({graphic, elapsed, remaining, theme, width, boxHeight}) => {
	const items = Array.isArray(graphic.props.items) ? graphic.props.items.map(String) : [];
	// ~137 px per row: shrink a long list to its box instead of letting it spill.
	const fit = Math.min(1, boxHeight / Math.max(1, items.length * 137));
	// Spread the reveals across the first 60% of the span so the last item has time to be read.
	const total = elapsed + remaining;
	const step = items.length > 1 ? Math.min(0.6, (total * 0.6) / items.length) : 0;
	return (
		<div style={{display: 'flex', flexDirection: 'column', gap: 22, width: width - 200, opacity: fadeOut(remaining), transform: `scale(${fit})`}}>
			{items.map((item, i) => {
				const k = enter(elapsed, i * step);
				return (
					<div
						key={i}
						style={{
							fontFamily: theme.fontFamily,
							fontWeight: theme.fontWeight,
							fontSize: 58,
							background: theme.panel,
							color: theme.panelText,
							border: theme.border,
							borderRadius: theme.radius,
							boxShadow: theme.shadow,
							padding: '22px 36px',
							display: 'flex',
							alignItems: 'center',
							gap: 24,
							opacity: clamp01(k * 2),
							transform: `translateX(${(1 - k) * -120}px)`,
							textTransform: theme.uppercase ? 'uppercase' : 'none',
						}}
					>
						<span style={{color: theme.accent, fontWeight: 900, fontSize: 64}}>{i + 1}</span>
						<span>{item}</span>
					</div>
				);
			})}
		</div>
	);
};

const LowerThird: React.FC<TemplateProps> = ({graphic, elapsed, remaining, theme, width}) => {
	const slide = clamp01(elapsed / 0.35);
	const x = (1 - (1 - Math.pow(1 - slide, 3))) * -(width);
	const out = 1 - fadeOut(remaining);
	return (
		<div
			style={{
				fontFamily: theme.fontFamily,
				background: theme.panel,
				color: theme.panelText,
				border: theme.border,
				borderLeft: `18px solid ${theme.accent}`,
				borderRadius: theme.radius,
				boxShadow: theme.shadow,
				padding: '26px 44px',
				minWidth: 560,
				transform: `translateX(${x - out * width}px)`,
			}}
		>
			<div style={{fontSize: 64, fontWeight: 900, textTransform: theme.uppercase ? 'uppercase' : 'none'}}>{str(graphic.props.title, str(graphic.props.text))}</div>
			{graphic.props.subtitle ? <div style={{fontSize: 40, fontWeight: theme.fontWeight, opacity: 0.8, marginTop: 6}}>{str(graphic.props.subtitle)}</div> : null}
		</div>
	);
};

const ProgressBar: React.FC<TemplateProps> = ({progress, theme, width}) => (
	<div style={{width, height: 14, background: 'rgba(255,255,255,0.25)'}}>
		<div style={{width: `${clamp01(progress) * 100}%`, height: '100%', background: theme.accent}} />
	</div>
);

/** Parse an SVG viewBox into its aspect ratio (width / height), 1.25 when unusable. */
export function viewBoxAspect(viewBox: string): number {
	const n = viewBox.trim().split(/[\s,]+/).map(Number);
	return n.length === 4 && n[2] > 0 && n[3] > 0 ? n[2] / n[3] : 1.25;
}

/**
 * Claude-drawn SVG art (already sanitized server-side). Layers pop in one after another, the whole
 * piece drifts in slowly (Ken Burns), and it fades out at the end. Sized to its box.
 */
const Illustration: React.FC<TemplateProps> = ({graphic, elapsed, remaining, progress, theme, boxWidth, boxHeight, mode}) => {
	const viewBox = str(graphic.props.viewBox, '0 0 1000 800');
	const defs = str(graphic.props.defs);
	const layers = Array.isArray(graphic.props.layers) ? graphic.props.layers.map(String) : [];
	const title = str(graphic.props.title);
	const titleSize = mode === 'speaker' ? 54 : 70;
	const titleH = title ? titleSize * 1.5 : 0;
	const aspect = viewBoxAspect(viewBox);
	const artW = Math.min(boxWidth, (boxHeight - titleH) * aspect);
	const artH = artW / aspect;
	const total = elapsed + remaining;
	const stagger = layers.length ? Math.min(0.2, (0.5 * total) / layers.length) : 0;
	const kTitle = enter(elapsed);
	return (
		<div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', opacity: fadeOut(remaining)}}>
			{title ? (
				<div
					style={{
						fontFamily: theme.fontFamily,
						fontWeight: 900,
						fontSize: titleSize,
						lineHeight: 1.2,
						height: titleH,
						maxWidth: boxWidth,
						whiteSpace: 'nowrap',
						overflow: 'hidden',
						color: theme.accent,
						textTransform: theme.uppercase ? 'uppercase' : 'none',
						WebkitTextStroke: '8px #000',
						paintOrder: 'stroke fill',
						opacity: clamp01(kTitle * 2),
						transform: `translateY(${(1 - kTitle) * 30}px)`,
					}}
				>
					{title}
				</div>
			) : null}
			<svg
				viewBox={viewBox}
				width={artW}
				height={artH}
				style={{
					transform: `scale(${1 + 0.05 * clamp01(progress)})`,
					borderRadius: mode === 'speaker' ? theme.radius : 0,
					filter: mode === 'speaker' ? 'drop-shadow(0 14px 30px rgba(0,0,0,0.5))' : undefined,
				}}
			>
				{defs ? <defs dangerouslySetInnerHTML={{__html: defs}} /> : null}
				{layers.map((layer, i) => {
					const k = clamp01((elapsed - i * stagger) / 0.35);
					const e = easeOutBack(k);
					return (
						<g
							key={i}
							style={{
								opacity: clamp01(k * 2.5),
								transform: `translateY(${(1 - e) * 40}px) scale(${0.85 + 0.15 * e})`,
								transformBox: 'fill-box',
								transformOrigin: 'center',
							}}
							dangerouslySetInnerHTML={{__html: layer}}
						/>
					);
				})}
			</svg>
		</div>
	);
};

const TEMPLATES: Record<Graphic['type'], React.FC<TemplateProps>> = {
	kinetic_text: KineticText,
	stat_card: StatCard,
	emoji_burst: EmojiBurst,
	list_build: ListBuild,
	lower_third: LowerThird,
	progress_bar: ProgressBar,
	illustration: Illustration,
};

/** How much a text graphic is enlarged when it is the full-frame visual. */
const VISUAL_TEXT_SCALE = 1.15;

/**
 * A graphic's template at source time t, unpositioned, laid out for a box of boxWidth x boxHeight.
 * Used for the split top panel and full-frame visuals (centered there) and by GraphicView.
 */
export const GraphicBody: React.FC<{
	graphic: Graphic;
	t: number;
	style: GraphicsStyle;
	width: number;
	height: number;
	boxWidth: number;
	boxHeight: number;
	mode: LayoutMode;
}> = ({graphic, t, style, width, height, boxWidth, boxHeight, mode}) => {
	const Template = TEMPLATES[graphic.type];
	if (!Template) return null;
	const dur = graphic.end - graphic.start;
	const grow = mode === 'visual' && graphic.type !== 'illustration' ? VISUAL_TEXT_SCALE : 1;
	const props: TemplateProps = {
		graphic,
		elapsed: t - graphic.start,
		remaining: graphic.end - t,
		progress: (t - graphic.start) / dur,
		theme: themeTokens(style),
		width: width / grow,
		height,
		boxWidth: boxWidth / grow,
		boxHeight: boxHeight / grow,
		mode,
	};
	if (grow === 1) return <Template {...props} />;
	return (
		<div style={{transform: `scale(${grow})`}}>
			<Template {...props} />
		</div>
	);
};

/** Where a placed (non-panel) graphic is centered vertically, as a fraction of output height. */
export function placedY(type: Graphic['type'], anchor: Graphic['anchor'], mode: LayoutMode, faceY: number, captionPos: 'top' | 'middle' | 'bottom'): number {
	if (mode === 'split') return type === 'lower_third' ? 0.88 : (SPLIT_AREA.top + SPLIT_AREA.bottom) / 2;
	// Over a full-frame visual, side graphics sit at the art's foot so they do not cover it.
	if (mode === 'visual') return VISUAL_AREA.bottom;
	// Over the speaker an emoji burst flanks the caption line, the part of the frame furthest from a face.
	if (type === 'emoji_burst') return CAPTION_Y[captionPos] - 0.06;
	return BAND_Y[placeGraphic(anchor, faceY, captionPos)];
}

/**
 * One graphic placed on the frame at source time t. The progress bar hugs the top edge. In speaker
 * mode the rest go in the band `placeGraphic` picks so they stay off the face (faceY) and the
 * captions; in split mode a lower third sits at the foot of the speaker panel; over a full-frame
 * visual they center. (Visual graphics in split/visual mode are drawn by the panel instead.)
 */
export const GraphicView: React.FC<{
	graphic: Graphic;
	t: number;
	style: GraphicsStyle;
	captionPos: 'top' | 'middle' | 'bottom';
	faceY: number;
	mode?: LayoutMode;
	width: number;
	height: number;
}> = ({graphic, t, style, captionPos, faceY, mode = 'speaker', width, height}) => {
	const body = (boxWidth: number, boxHeight: number) => (
		<GraphicBody graphic={graphic} t={t} style={style} width={width} height={height} boxWidth={boxWidth} boxHeight={boxHeight} mode={mode} />
	);
	if (graphic.type === 'progress_bar') {
		return <div style={{position: 'absolute', left: 0, top: 0}}>{body(width, 14)}</div>;
	}
	const y = placedY(graphic.type, graphic.anchor, mode, faceY, captionPos);
	// Lower thirds are left-aligned; the rest are centered on the band.
	const left = graphic.type === 'lower_third';
	return (
		<div
			style={{
				position: 'absolute',
				left: 0,
				right: left ? undefined : 0,
				top: y * height,
				transform: 'translateY(-50%)',
				display: 'flex',
				justifyContent: left ? 'flex-start' : 'center',
				overflow: left ? 'hidden' : undefined,
			}}
		>
			{/* An illustration over the speaker is a card the size of a band, not a full panel. */}
			{body(graphic.type === 'illustration' ? width * 0.7 : width, graphic.type === 'illustration' ? height * 0.26 : height * 0.3)}
		</div>
	);
};
