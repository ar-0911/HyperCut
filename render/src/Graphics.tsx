import React from 'react';
import {BAND_Y, placeGraphic} from './layout';
import type {Graphic, GraphicsStyle} from './plan';
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
	width: number;
	height: number;
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

const EmojiBurst: React.FC<TemplateProps> = ({graphic, elapsed, remaining}) => {
	const emoji = str(graphic.props.emoji, '🔥');
	const count = Math.min(14, Math.max(3, Number(graphic.props.count ?? 8)));
	return (
		<div style={{position: 'relative', width: 0, height: 0, opacity: fadeOut(remaining)}}>
			{Array.from({length: count}, (_, i) => {
				// Deterministic fan-out: no Math.random, so every render of a frame is identical.
				const angle = (i / count) * Math.PI * 2 + 0.3 * (i % 2);
				const reach = (260 + (i % 3) * 90) * clamp01(elapsed / 0.5);
				const x = Math.cos(angle) * reach;
				const y = Math.sin(angle) * reach * 0.8 - elapsed * 60;
				const size = 120 + (i % 3) * 36;
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

const ListBuild: React.FC<TemplateProps> = ({graphic, elapsed, remaining, theme, width}) => {
	const items = Array.isArray(graphic.props.items) ? graphic.props.items.map(String) : [];
	// Spread the reveals across the first 60% of the span so the last item has time to be read.
	const total = elapsed + remaining;
	const step = items.length > 1 ? Math.min(0.6, (total * 0.6) / items.length) : 0;
	return (
		<div style={{display: 'flex', flexDirection: 'column', gap: 22, width: width - 200, opacity: fadeOut(remaining)}}>
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

const TEMPLATES: Record<Graphic['type'], React.FC<TemplateProps>> = {
	kinetic_text: KineticText,
	stat_card: StatCard,
	emoji_burst: EmojiBurst,
	list_build: ListBuild,
	lower_third: LowerThird,
	progress_bar: ProgressBar,
};

/**
 * One graphic at source time t. The progress bar hugs the top edge; everything else goes in the band
 * `placeGraphic` picks so it stays off the face (faceY) and the captions.
 */
export const GraphicView: React.FC<{
	graphic: Graphic;
	t: number;
	style: GraphicsStyle;
	captionPos: 'top' | 'middle' | 'bottom';
	faceY: number;
	width: number;
	height: number;
}> = ({graphic, t, style, captionPos, faceY, width, height}) => {
	const Template = TEMPLATES[graphic.type];
	if (!Template) return null;
	const theme = themeTokens(style);
	const dur = graphic.end - graphic.start;
	const props: TemplateProps = {
		graphic,
		elapsed: t - graphic.start,
		remaining: graphic.end - t,
		progress: (t - graphic.start) / dur,
		theme,
		width,
		height,
	};
	if (graphic.type === 'progress_bar') {
		return (
			<div style={{position: 'absolute', left: 0, top: 0}}>
				<Template {...props} />
			</div>
		);
	}
	const band = placeGraphic(graphic.anchor, faceY, captionPos);
	// Lower thirds are left-aligned; the rest are centered on the band.
	const left = graphic.type === 'lower_third';
	return (
		<div
			style={{
				position: 'absolute',
				left: 0,
				right: left ? undefined : 0,
				top: BAND_Y[band] * height,
				transform: 'translateY(-50%)',
				display: 'flex',
				justifyContent: left ? 'flex-start' : 'center',
				overflow: left ? 'hidden' : undefined,
			}}
		>
			<Template {...props} />
		</div>
	);
};
