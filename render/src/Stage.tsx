// Stage graphics (ADR 0611): what the speaker talks about, drawn behind the cut-out speaker. Cards slide out
// from behind them into the free side of the frame; a scene replaces the room and a chart builds behind
// them while the speaker is pulled back (layout.ts pullAt) so it shows. All pure functions of time.

import React from 'react';
import {AbsoluteFill} from 'remotion';
import {captionFamily} from './fonts';
import {freeSide, PULL_BACK} from './layout';
import type {EditPlan, Graphic} from './plan';

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const easeOutCubic = (k: number) => 1 - Math.pow(1 - k, 3);
const easeOutBack = (k: number) => 1 + 2.2 * Math.pow(k - 1, 3) + 1.2 * Math.pow(k - 1, 2);
const str = (v: unknown, fallback = '') => (v === undefined || v === null ? fallback : String(v));

type Art = {viewBox: string; defs: string; layers: string[]};
const artOf = (p: Record<string, unknown>): Art | null =>
	Array.isArray(p.layers) && p.layers.length ? {viewBox: str(p.viewBox, '0 0 1000 800'), defs: str(p.defs), layers: p.layers.map(String)} : null;

/** Prefix the ids in a Claude-drawn SVG so several on screen can't take each other's gradients. */
export function scopeIds(markup: string, prefix: string): string {
	return markup
		.replace(/\bid="([^"]+)"/g, (_, id) => `id="${prefix}${id}"`)
		.replace(/url\(#([^)]+)\)/g, (_, id) => `url(#${prefix}${id})`)
		.replace(/href="#([^"]+)"/g, (_, id) => `href="#${prefix}${id}"`);
}

const ArtSvg: React.FC<{art: Art; prefix: string; width: number; height: number; slice?: boolean; reveal?: number}> = ({art, prefix, width, height, slice, reveal = 99}) => (
	<svg viewBox={art.viewBox} width={width} height={height} preserveAspectRatio={slice ? 'xMidYMid slice' : 'xMidYMid meet'} style={{display: 'block'}}>
		{art.defs ? <defs dangerouslySetInnerHTML={{__html: scopeIds(art.defs, prefix)}} /> : null}
		{art.layers.map((layer, i) => {
			const k = clamp01(reveal - i * 0.6);
			return <g key={i} style={{opacity: k, transform: `translateY(${(1 - easeOutCubic(k)) * 30}px)`}} dangerouslySetInnerHTML={{__html: scopeIds(layer, prefix)}} />;
		})}
	</svg>
);

/** Where the face is once the speaker is pulled back by `pull` (0..1) about the bottom of the frame and
 * moved `shift` px sideways. */
export function pulledFace(face: {x: number; y: number}, height: number, pull: number, shift = 0) {
	const s = 1 - PULL_BACK * pull;
	return {x: face.x + shift, y: height - (height - face.y) * s, scale: s};
}

type Colors = {accent: string; second: string; panel: string; font: string};
const colorsOf = (plan: EditPlan): Colors => ({
	accent: plan.style.graphics.accent_color,
	second: plan.style.graphics.secondary_color || plan.style.graphics.accent_color,
	panel: plan.style.graphics.panel_color || '#0E1330',
	font: `"${captionFamily(plan.style.caption.font)}", Inter, sans-serif`,
});

export {freeSide};

/** Card boxes (output px) for n cards on one side: stacked down the free side, upper frame first. */
export function cardBoxes(n: number, side: 'left' | 'right', width: number, height: number) {
	const w = Math.round(0.38 * width);
	const h = Math.round(w * 0.8 + 0.075 * width);
	const gap = 0.025 * height;
	const top0 = n === 1 ? 0.16 * height : 0.07 * height;
	const x = side === 'left' ? 0.035 * width : width - 0.035 * width - w;
	return Array.from({length: n}, (_, i) => ({x, y: top0 + i * (h + gap), w, h}));
}

const Cards: React.FC<{g: Graphic; t: number; width: number; height: number; face: {x: number; y: number}; side: 'left' | 'right'; c: Colors}> = ({g, t, width, height, face, side, c}) => {
	const cards = (Array.isArray(g.props.cards) ? g.props.cards : []).filter((x): x is Record<string, unknown> => !!x && typeof x === 'object').slice(0, 3);
	const boxes = cardBoxes(cards.length, side, width, height);
	const dir = side === 'left' ? 1 : -1;
	return (
		<AbsoluteFill style={{perspective: 1600}}>
			{cards.map((card, i) => {
				const b = boxes[i];
				const k = easeOutCubic(clamp01((t - g.start - 0.3 * i) / 0.6));
				const out = clamp01((g.end - t) / 0.35);
				// From behind the head (the speaker hides it there) out to its place.
				const fromX = face.x - b.w / 2;
				const x = fromX + (b.x - fromX) * k;
				const y = face.y - b.h / 2 + (b.y - (face.y - b.h / 2)) * k;
				const art = artOf(card);
				const artH = b.w * 0.8;
				const title = str(card.title);
				return (
					<div
						key={i}
						style={{
							position: 'absolute',
							left: x,
							top: y,
							width: b.w,
							height: b.h,
							opacity: clamp01(k * 3) * out,
							transform: `rotateY(${dir * 16 * (0.6 + 0.4 * k)}deg) rotateZ(${(i % 2 ? 2.5 : -3.5) * dir}deg) scale(${0.82 + 0.18 * k})`,
							borderRadius: 0.032 * width,
							overflow: 'hidden',
							background: '#F6F4EF',
							boxShadow: '0 30px 60px rgba(8,10,30,0.45)',
						}}
					>
						{art ? (
							<ArtSvg art={art} prefix={`${g.id}c${i}-`} width={b.w} height={artH} slice reveal={(t - g.start - 0.3 * i) * 4} />
						) : (
							<div style={{height: artH, background: `linear-gradient(140deg, ${c.second}, ${c.accent})`}} />
						)}
						<div
							style={{
								position: 'absolute',
								left: 0,
								right: 0,
								bottom: 0,
								height: b.h - artH,
								display: 'flex',
								alignItems: 'center',
								gap: 0.013 * width,
								padding: `0 ${0.028 * width}px`,
								background: c.panel,
								color: '#fff',
								fontFamily: c.font,
								fontWeight: 800,
								// Fit one line: the label's room after the padding and the dot, at about 0.66 em a capital.
								fontSize: Math.min(0.037 * width, (b.w - 0.1 * width) / (Math.max(1, title.length) * 0.66)),
								textTransform: 'uppercase',
								letterSpacing: 0.5,
								whiteSpace: 'nowrap',
								overflow: 'hidden',
							}}
						>
							<span style={{width: 0.013 * width, height: 0.013 * width, borderRadius: '50%', background: c.accent, flex: 'none'}} />
							{title}
						</div>
					</div>
				);
			})}
		</AbsoluteFill>
	);
};

const Scene: React.FC<{g: Graphic; t: number; width: number; height: number; c: Colors}> = ({g, t, width, height, c}) => {
	const art = artOf(g.props);
	const k = clamp01(Math.min((t - g.start) / 0.4, (g.end - t) / 0.4));
	const p = clamp01((t - g.start) / Math.max(0.1, g.end - g.start));
	return (
		<AbsoluteFill style={{opacity: k}}>
			<AbsoluteFill style={{background: art ? '#F6F4EF' : `linear-gradient(170deg, ${c.second}, ${c.panel})`}} />
			{art ? (
				<AbsoluteFill style={{transform: `scale(${1.04 + 0.06 * p})`, filter: 'blur(2px) saturate(1.05)'}}>
					<ArtSvg art={art} prefix={`${g.id}-`} width={width} height={height} slice />
				</AbsoluteFill>
			) : null}
			{/* Depth: the edges fall off into the panel colour, so the speaker reads in front. */}
			<AbsoluteFill style={{background: `radial-gradient(ellipse at 50% 45%, transparent 35%, color-mix(in srgb, ${c.panel} 55%, transparent) 100%)`}} />
		</AbsoluteFill>
	);
};

/** Split a headline into its leading number and the words after it, for two-colour type. */
export function splitHeadline(text: string): [string, string] {
	const m = text.trim().match(/^([^\s]*\d[^\s]*)\s*(.*)$/);
	return m ? [m[1], m[2]] : ['', text.trim()];
}

/** Chart points in a plot box: values scaled from 0 (or the minimum, if negative) to the maximum. */
export function chartPoints(values: number[], w: number, h: number) {
	const lo = Math.min(0, ...values);
	const hi = Math.max(...values);
	const span = hi - lo || 1;
	return values.map((v, i) => ({x: values.length === 1 ? w / 2 : (i * w) / (values.length - 1), y: h - ((v - lo) / span) * h}));
}

const formatValue = (v: number) => (Math.abs(v) >= 1000 ? `${Math.round(v / 100) / 10}k` : String(Math.round(v * 10) / 10));

const Chart: React.FC<{g: Graphic; t: number; width: number; height: number; c: Colors}> = ({g, t, width, height, c}) => {
	const values = (Array.isArray(g.props.values) ? g.props.values : []).map(Number).filter(Number.isFinite);
	if (values.length < 2) return null;
	const labels = (Array.isArray(g.props.labels) ? g.props.labels : []).map((x) => str(x));
	const unit = str(g.props.unit);
	const bars = g.props.kind === 'bars';
	const e = t - g.start;
	const inK = easeOutCubic(clamp01(e / 0.45));
	const out = clamp01((g.end - t) / 0.35);
	const [num, rest] = splitHeadline(str(g.props.headline));
	const headSize = Math.min(0.16 * width, (0.92 * width) / Math.max(4, (num + ' ' + rest).length * 0.6));
	const panel = {x: 0.04 * width, y: 0.155 * height, w: 0.92 * width, h: 0.4 * height};
	const pad = {l: 0.07 * width, r: 0.09 * width, t: 0.07 * height, b: 0.06 * height};
	const plotW = panel.w - pad.l - pad.r;
	const plotH = panel.h - pad.t - pad.b;
	const pts = chartPoints(values, plotW, plotH);
	const barX = (i: number) => ((i + 0.5) * plotW) / values.length;
	const draw = clamp01((e - 0.35) / 1.2); // how much of the data is in
	const last = pts[pts.length - 1];
	const path = pts.map((p, i) => `${i ? 'L' : 'M'}${p.x},${p.y}`).join(' ');
	let length = 0;
	for (let i = 1; i < pts.length; i++) length += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
	const done = clamp01((e - 1.5) / 0.4);
	const font = c.font;
	return (
		<AbsoluteFill style={{opacity: out}}>
			<div
				style={{
					position: 'absolute',
					left: 0,
					right: 0,
					top: 0.05 * height,
					textAlign: 'center',
					fontFamily: font,
					fontWeight: 900,
					fontSize: headSize,
					lineHeight: 1,
					letterSpacing: -headSize * 0.03,
					color: '#fff',
					textTransform: 'uppercase',
					opacity: inK,
					transform: `translateY(${(1 - inK) * 40}px)`,
					textShadow: '0 10px 40px rgba(0,0,0,0.35)',
				}}
			>
				{num ? <span>{num} </span> : null}
				<span style={{color: c.accent}}>{rest}</span>
			</div>
			<div
				style={{
					position: 'absolute',
					left: panel.x,
					top: panel.y + (1 - inK) * 60,
					width: panel.w,
					height: panel.h,
					borderRadius: 0.037 * width,
					background: c.panel,
					boxShadow: '0 40px 80px rgba(0,0,0,0.5)',
					opacity: inK,
					overflow: 'hidden',
				}}
			>
				<svg width={panel.w} height={panel.h} style={{position: 'absolute', inset: 0}}>
					<defs>
						<linearGradient id={`${g.id}-fill`} x1="0" y1="0" x2="0" y2="1">
							<stop offset="0" stopColor={c.accent} stopOpacity={0.45} />
							<stop offset="1" stopColor={c.accent} stopOpacity={0} />
						</linearGradient>
						<clipPath id={`${g.id}-clip`}>
							<rect x={0} y={-20} width={plotW * draw} height={plotH + 40} />
						</clipPath>
					</defs>
					<g transform={`translate(${pad.l},${pad.t})`}>
						{[0, 0.25, 0.5, 0.75, 1].map((f) => (
							<line key={f} x1={0} x2={plotW} y1={plotH * f} y2={plotH * f} stroke="#fff" strokeOpacity={0.1} strokeWidth={2} />
						))}
						{bars
							? pts.map((p, i) => {
									const k = easeOutBack(clamp01((e - 0.35 - 0.12 * i) / 0.5));
									const bw = (plotW / values.length) * 0.62;
									const h = (plotH - p.y) * k;
									return (
										<rect
											key={i}
											x={barX(i) - bw / 2}
											y={plotH - h}
											width={bw}
											height={Math.max(0, h)}
											rx={bw * 0.12}
											fill={i === values.length - 1 ? c.accent : c.second}
											opacity={i === values.length - 1 ? 1 : 0.75}
										/>
									);
								})
							: (
								<>
									<path d={`${path} L${last.x},${plotH} L0,${plotH} Z`} fill={`url(#${g.id}-fill)`} clipPath={`url(#${g.id}-clip)`} />
									<path
										d={path}
										fill="none"
										stroke={c.accent}
										strokeWidth={0.011 * width}
										strokeLinecap="round"
										strokeLinejoin="round"
										strokeDasharray={length}
										strokeDashoffset={length * (1 - draw)}
									/>
									{pts.map((p, i) => {
										const at = pts.length === 1 ? 1 : i / (pts.length - 1);
										const k = easeOutBack(clamp01((draw - at) * 6 + (i === 0 ? 1 : 0)));
										return <circle key={i} cx={p.x} cy={p.y} r={0.012 * width * k} fill="#fff" stroke={c.accent} strokeWidth={0.005 * width} />;
									})}
								</>
							)}
						{labels.map((l, i) =>
							l ? (
								<text
									key={i}
									x={bars ? barX(i) : pts[i].x}
									y={plotH + 0.035 * height}
									textAnchor="middle"
									fill="#fff"
									fillOpacity={0.6 * inK}
									style={{fontFamily: font, fontWeight: 700, fontSize: 0.026 * width}}
								>
									{l}
								</text>
							) : null,
						)}
					</g>
				</svg>
			</div>
			{/* The final value, popping in once the data is drawn. */}
			<div
				style={{
					position: 'absolute',
					left: panel.x + pad.l + (bars ? barX(values.length - 1) : last.x),
					top: panel.y + pad.t + last.y - 0.045 * height,
					transform: `translate(-50%, -50%) scale(${easeOutBack(done)})`,
					padding: `${0.008 * height}px ${0.026 * width}px`,
					borderRadius: 999,
					background: c.second,
					color: '#fff',
					fontFamily: font,
					fontWeight: 900,
					fontSize: 0.042 * width,
					whiteSpace: 'nowrap',
					boxShadow: '0 14px 30px rgba(0,0,0,0.35)',
					opacity: done,
				}}
			>
				{formatValue(values[values.length - 1])}
				{unit ? ` ${unit}` : ''}
			</div>
		</AbsoluteFill>
	);
};

/** CSS filter for the real footage under stage graphics. It is covered by the scene or the studio backdrop
 * (the pulled-back speaker would leave a ghost of itself), but shows through while they fade in and out. */
export function stageFootageFilter(stage: Graphic[]): string | undefined {
	return stage.length ? 'blur(16px) brightness(0.6) saturate(0.8)' : undefined;
}

/** Stage graphics at source time t, drawn behind the cut-out speaker. `face` is the face before pull-back. */
export const StageLayer: React.FC<{graphics: Graphic[]; t: number; plan: EditPlan; face: {x: number; y: number}; pull: number; shift: number}> = ({
	graphics,
	t,
	plan,
	face,
	pull,
	shift,
}) => {
	const {width, height} = plan.output;
	const c = colorsOf(plan);
	const f = pulledFace(face, height, pull, shift);
	const side = freeSide(face.x, width);
	const studio = !graphics.some((g) => g.type === 'scene');
	return (
		<AbsoluteFill>
			{studio ? (
				// A dark studio backdrop behind a chart, with a soft glow of the accent.
				<AbsoluteFill
					style={{
						opacity: pull,
						background: [
							`radial-gradient(circle at 50% 30%, color-mix(in srgb, ${c.second} 30%, transparent) 0%, transparent 55%)`,
							`radial-gradient(circle at 80% 85%, color-mix(in srgb, ${c.accent} 18%, transparent) 0%, transparent 45%)`,
							`linear-gradient(170deg, color-mix(in srgb, ${c.panel} 80%, #fff) 0%, ${c.panel} 60%, #05060F 100%)`,
						].join(', '),
					}}
				/>
			) : null}
			{graphics.map((g) =>
				g.type === 'scene' ? (
					<Scene key={g.id} g={g} t={t} width={width} height={height} c={c} />
				) : g.type === 'chart' ? (
					<Chart key={g.id} g={g} t={t} width={width} height={height} c={c} />
				) : g.type === 'card_stack' ? (
					<Cards key={g.id} g={g} t={t} width={width} height={height} face={f} side={side} c={c} />
				) : null,
			)}
		</AbsoluteFill>
	);
};
