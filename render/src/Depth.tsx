// Green-screen effects (ADR 0901): what is drawn behind the cut-out speaker. The speaker's pixels are never
// changed; the cut-out video is the same footage with everything but the speaker made transparent.

import React from 'react';
import {AbsoluteFill, Img, OffthreadVideo} from 'remotion';
import {StudioBackdrop} from './Backdrop';
import {captionFamily} from './fonts';
import {GraphicBody} from './Graphics';
import type {BackgroundSpan, EditPlan, Graphic} from './plan';

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const easeOutCubic = (k: number) => 1 - Math.pow(1 - k, 3);

/** Blur of the real background in the "blur" kind, in output pixels. */
export const BG_BLUR = 22;
/** Brightness of the real background in the "dim" kind. */
export const BG_DIM = 0.38;
/** Font of the big titles behind the speaker: tall and heavy, so a head can cover part of it and it still reads. */
export const TITLE_FONT = 'Anton';
/**
 * Title center above the face, as a fraction of output height, when the plan has no `props.y` (set from
 * the cut-out by hypercut.matte.titles): the top of the head covers the bottom of the letters.
 */
export const TITLE_ABOVE_FACE = 0.2;

/** CSS filter for the real background (original, blur, dim); undefined when it is shown as is. */
export function backgroundFilter(kind: BackgroundSpan['kind']): string | undefined {
	if (kind === 'blur') return `blur(${BG_BLUR}px) brightness(0.85)`;
	if (kind === 'dim') return `brightness(${BG_DIM}) saturate(0.8)`;
	return undefined;
}

/** Whether the real background is hidden under a replacement (colour, gradient, imported media). */
export const replacesBackground = (kind: BackgroundSpan['kind']) => kind === 'color' || kind === 'gradient' || kind === 'media';

/**
 * Font size (px) that fits `text` on one line across `width`. Anton's capitals are about 0.48 em wide;
 * capped so short words don't fill half the frame.
 */
export function titleSize(text: string, width: number): number {
	const chars = Math.max(1, [...text].length);
	return Math.round(Math.min(width * 0.36, (width * 0.92) / (chars * 0.48)));
}

/** Slow drift and breathing scale of a replaced background, 0 = still. A pure function of time. */
export function parallaxTransform(parallax: number, seconds: number): string {
	if (!parallax) return 'none';
	const scale = 1.06 + 0.06 * parallax * (0.5 + 0.5 * Math.sin(seconds * 0.35));
	const x = 2.5 * parallax * Math.sin(seconds * 0.22);
	const y = 1.5 * parallax * Math.cos(seconds * 0.17);
	return `scale(${scale}) translate(${x}%, ${y}%)`;
}

/** The replacement background (the studio set, tinted or not, or an imported picture/clip) filling its box. */
export const BackgroundFill: React.FC<{
	bg: BackgroundSpan;
	accent: string;
	seconds: number;
	mediaSrc?: (name: string) => string;
	backdrop: React.ReactNode;
}> = ({bg, accent, seconds, mediaSrc, backdrop}) => {
	const transform = parallaxTransform(bg.parallax, seconds);
	const fill: React.CSSProperties = {position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover'};
	let body: React.ReactNode = backdrop;
	if (bg.kind === 'color') {
		const c = bg.color || accent;
		// Never a flat colour (ADR 0613): the studio set, its light washed with the colour asked for.
		body = <StudioBackdrop seconds={seconds} tint={c} />;
	} else if (bg.kind === 'media' && bg.src && mediaSrc) {
		const src = mediaSrc(bg.src);
		body = /\.(mp4|mov|webm|m4v)$/i.test(bg.src) ? <OffthreadVideo src={src} muted style={fill} /> : <Img src={src} style={fill} />;
	}
	return <AbsoluteFill style={{transform, transformOrigin: '50% 40%'}}>{body}</AbsoluteFill>;
};

/** A big title behind the speaker's head: rises into place, holds, fades. */
export const BehindTitle: React.FC<{graphic: Graphic; t: number; plan: EditPlan; faceX: number; faceY: number}> = ({graphic, t, plan, faceX, faceY}) => {
	const {width, height} = plan.output;
	const text = String(graphic.props.text ?? '').toUpperCase();
	if (!text) return null;
	const size = titleSize(text, width);
	const k = easeOutCubic(clamp01((t - graphic.start) / 0.45));
	const out = clamp01((graphic.end - t) / 0.25);
	const planned = typeof graphic.props.y === 'number' ? graphic.props.y : null;
	const y = (planned ?? Math.max(0.1, faceY - TITLE_ABOVE_FACE)) * height;
	// Centered on the frame (where the placement measured it), nudged toward the face when unplaced.
	const x = planned === null ? width / 2 + (faceX - width / 2) * 0.35 : width / 2;
	const accent = plan.style.graphics.accent_color;
	return (
		<div
			style={{
				position: 'absolute',
				left: x,
				top: Math.max(size * 0.55, y),
				transform: `translate(-50%, -50%) translateY(${(1 - k) * size * 0.35}px) scale(${0.92 + 0.08 * k})`,
				opacity: k * out,
				fontFamily: `"${captionFamily(TITLE_FONT)}", Impact, sans-serif`,
				fontSize: size,
				lineHeight: 1,
				whiteSpace: 'nowrap',
				color: graphic.props.color ? String(graphic.props.color) : accent,
				letterSpacing: size * 0.01,
				textShadow: '0 8px 40px rgba(0,0,0,0.35)',
			}}
		>
			{text}
		</div>
	);
};

/**
 * Everything drawn behind the speaker at source time t: big titles around the head, and any other graphic
 * filling the frame behind them (an illustration or picture the speaker stands in front of).
 */
export const BehindLayer: React.FC<{graphics: Graphic[]; t: number; plan: EditPlan; face: {x: number; y: number}; renderMedia: (g: Graphic) => React.ReactNode}> = ({
	graphics,
	t,
	plan,
	face,
	renderMedia,
}) => {
	const {width, height} = plan.output;
	return (
		<AbsoluteFill>
			{graphics.map((g) => {
				if (g.type === 'kinetic_text') return <BehindTitle key={g.id} graphic={g} t={t} plan={plan} faceX={face.x} faceY={face.y / height} />;
				if (g.type === 'media') return <React.Fragment key={g.id}>{renderMedia(g)}</React.Fragment>;
				return (
					<AbsoluteFill key={g.id} style={{alignItems: 'center', justifyContent: 'flex-start', paddingTop: height * 0.06}}>
						<GraphicBody graphic={g} t={t} style={plan.style.graphics} width={width} height={height} boxWidth={width * 0.94} boxHeight={height * 0.5} mode="visual" />
					</AbsoluteFill>
				);
			})}
		</AbsoluteFill>
	);
};
