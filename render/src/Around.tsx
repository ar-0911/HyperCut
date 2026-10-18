// Effects around the cut-out speaker (ADR 0610): orbit, fly_out and particles. Each is one pure function of
// time giving every element a position and a depth; elements with depth < 0.5 are drawn behind the speaker
// (before the cut-out), the rest in front, and a front element fades out before it can reach the face.

import React from 'react';
import {AbsoluteFill} from 'remotion';
import type {EditPlan, Graphic} from './plan';

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const easeOutCubic = (k: number) => 1 - Math.pow(1 - k, 3);

/** One element of an effect at a moment, in output pixels. depth: 0 far behind .. 1 close to the camera. */
export type Element = {
	key: string;
	x: number;
	y: number;
	/** Diameter-ish size in px, used for drawing and to keep it off the face. */
	size: number;
	depth: number;
	opacity: number;
	rotate: number;
	content: {kind: 'item'; text: string} | {kind: 'particle'; particle: ParticleKind; hue: number};
};
export type ParticleKind = 'sparkles' | 'bokeh' | 'confetti' | 'embers';

/** The face area no front element may cover (output pixels), around the tracked face point. */
export function faceBox(face: {x: number; y: number}, width: number, height: number) {
	return {x0: face.x - 0.17 * width, x1: face.x + 0.17 * width, y0: face.y - 0.13 * height, y1: face.y + 0.11 * height};
}

/** 1 when a front element of this size is clear of the face box, easing to 0 as it gets within a margin of it. */
export function faceClearance(e: {x: number; y: number; size: number}, box: ReturnType<typeof faceBox>): number {
	const dx = Math.max(box.x0 - e.x, 0, e.x - box.x1);
	const dy = Math.max(box.y0 - e.y, 0, e.y - box.y1);
	const gap = Math.hypot(dx, dy) - e.size / 2;
	return clamp01(gap / 60);
}

const fadeInOut = (g: Graphic, t: number, inS = 0.35, outS = 0.35) => clamp01((t - g.start) / inS) * clamp01((g.end - t) / outS);
const itemsOf = (g: Graphic): string[] => (Array.isArray(g.props.items) ? g.props.items.map(String).filter(Boolean) : []);

/** Deterministic 0..1 noise from a string and an index (no Math.random: frames must be pure). */
export function rand(seed: string, i: number): number {
	let h = 2166136261 ^ i;
	for (let k = 0; k < seed.length; k++) h = Math.imul(h ^ seed.charCodeAt(k), 16777619);
	h = Math.imul(h ^ (h >>> 15), 2246822507);
	h = Math.imul(h ^ (h >>> 13), 3266489909);
	return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

/** A ring of items circling the speaker's shoulders: behind on the far side, in front on the near side. */
function orbit(g: Graphic, t: number, face: {x: number; y: number}, width: number, height: number): Element[] {
	const items = itemsOf(g);
	if (!items.length) return [];
	const k = t - g.start;
	const grow = 0.6 + 0.4 * easeOutCubic(clamp01(k / 0.6));
	const cx = face.x;
	const cy = face.y + 0.16 * height;
	const rx = 0.38 * width * grow;
	const ry = 0.05 * height * grow;
	const fade = fadeInOut(g, t);
	return items.map((text, i) => {
		const theta = (2 * Math.PI * i) / items.length + 1.1 * k;
		const near = (Math.sin(theta) + 1) / 2;
		return {
			key: `${g.id}-${i}`,
			x: cx + rx * Math.cos(theta),
			y: cy + ry * Math.sin(theta),
			size: 120 * (0.7 + 0.45 * near),
			depth: near,
			opacity: fade * (0.65 + 0.35 * near),
			rotate: 8 * Math.cos(theta),
			content: {kind: 'item', text},
		};
	});
}

/** Directions (screen angle, degrees) items burst toward: up-left, up-right, left, right, then repeat. */
const BURST = [200, -20, 165, 15, 225, -45];

/** Items bursting out from behind the head toward the camera, one after another. */
function flyOut(g: Graphic, t: number, face: {x: number; y: number}, width: number, height: number): Element[] {
	const items = itemsOf(g);
	const life = 1.4;
	const gap = Math.min(0.35, Math.max(0.1, (g.end - g.start - life) / Math.max(1, items.length - 1)));
	const out: Element[] = [];
	items.forEach((text, i) => {
		const k = (t - g.start - i * gap) / life;
		if (k < 0 || k > 1) return;
		const e = easeOutCubic(k);
		const a = (BURST[i % BURST.length] * Math.PI) / 180;
		const dist = e * 0.62 * width;
		out.push({
			key: `${g.id}-${i}`,
			x: face.x + Math.cos(a) * dist,
			y: face.y - 0.06 * height + Math.sin(a) * dist * 0.8 + 0.12 * height * k * k,
			size: 120 * (0.35 + 1.5 * e),
			// Behind the head while it rises, then in front once it has come out.
			depth: clamp01((k - 0.22) * 4),
			opacity: clamp01(k / 0.12) * clamp01((1 - k) / 0.25),
			rotate: (i % 2 ? 1 : -1) * 18 * (1 - e),
			content: {kind: 'item', text},
		});
	});
	return out;
}

const PARTICLES = 34;

/** Atmosphere drifting around the speaker, some far behind, some close to the camera. */
function particles(g: Graphic, t: number, width: number, height: number): Element[] {
	const kind = (['sparkles', 'bokeh', 'confetti', 'embers'] as const).find((k) => k === g.props.kind) ?? 'sparkles';
	const k = t - g.start;
	const fade = fadeInOut(g, t, 0.6, 0.6);
	const falls = kind === 'confetti';
	const out: Element[] = [];
	for (let i = 0; i < PARTICLES; i++) {
		const r = (j: number) => rand(g.id + kind, i * 7 + j);
		const depth = r(0);
		const speed = (falls ? 0.16 : 0.07) * (0.6 + depth) * height;
		const travel = height * 1.2;
		const y0 = r(1) * travel;
		const along = (y0 + speed * k) % travel;
		const y = falls ? along - 0.1 * height : height * 1.1 - along;
		const sway = Math.sin(k * (0.6 + r(2)) + r(3) * 6.28) * 0.04 * width;
		const base = kind === 'bokeh' ? 70 : kind === 'confetti' ? 34 : kind === 'embers' ? 16 : 30;
		const twinkle = kind === 'sparkles' ? 0.55 + 0.45 * Math.sin(k * 4 + r(4) * 6.28) : 1;
		out.push({
			key: `${g.id}-${i}`,
			x: r(5) * width + sway,
			y,
			size: base * (0.5 + 1.3 * depth),
			depth,
			opacity: fade * twinkle * (kind === 'bokeh' ? 0.35 + 0.3 * depth : 0.75 + 0.25 * depth),
			rotate: kind === 'confetti' ? k * 220 * (r(6) - 0.5) + r(6) * 360 : 0,
			content: {kind: 'particle', particle: kind, hue: r(6)},
		});
	}
	return out;
}

/** Every element of an effect around the speaker at source time t. */
export function aroundElements(g: Graphic, t: number, face: {x: number; y: number}, width: number, height: number): Element[] {
	if (g.type === 'orbit') return orbit(g, t, face, width, height);
	if (g.type === 'fly_out') return flyOut(g, t, face, width, height);
	if (g.type === 'particles') return particles(g, t, width, height);
	return [];
}

/** Which elements a pass draws: behind the speaker, in front of them, or all (no cut-out: all in front). */
export type Pass = 'behind' | 'front' | 'all';

/** Elements to draw in one pass: behind the speaker, or in front of them and clear of the face. */
export function passElements(els: Element[], pass: Pass, box: ReturnType<typeof faceBox>): Element[] {
	if (pass === 'behind') return els.filter((e) => e.depth < 0.5);
	return els
		.filter((e) => pass === 'all' || e.depth >= 0.5)
		.map((e) => ({...e, opacity: e.opacity * faceClearance(e, box)}))
		.filter((e) => e.opacity > 0.01);
}

const CONFETTI = ['#FFE600', '#FF4FA3', '#4F8CFF', '#3DDC97', '#FF8A3D', '#FFFFFF'];
const isEmoji = (s: string) => /\p{Extended_Pictographic}/u.test(s);

const ElementView: React.FC<{e: Element; accent: string}> = ({e, accent}) => {
	const pos: React.CSSProperties = {
		position: 'absolute',
		left: e.x,
		top: e.y,
		transform: `translate(-50%, -50%) rotate(${e.rotate}deg)`,
		opacity: e.opacity,
	};
	if (e.content.kind === 'item') {
		const {text} = e.content;
		if (isEmoji(text)) {
			return (
				<div style={{...pos, fontSize: e.size, lineHeight: 1, fontFamily: '"Noto Color Emoji", "Apple Color Emoji", "Segoe UI Emoji", sans-serif', filter: 'drop-shadow(0 10px 18px rgba(0,0,0,0.35))'}}>
					{text}
				</div>
			);
		}
		return (
			<div
				style={{
					...pos,
					fontSize: e.size * 0.42,
					fontFamily: '"Montserrat", "Inter", sans-serif',
					fontWeight: 900,
					whiteSpace: 'nowrap',
					padding: `${e.size * 0.12}px ${e.size * 0.24}px`,
					borderRadius: e.size,
					background: '#FFFFFF',
					color: '#111111',
					border: `${Math.max(3, e.size * 0.04)}px solid ${accent}`,
					boxShadow: '0 12px 30px rgba(0,0,0,0.35)',
				}}
			>
				{text}
			</div>
		);
	}
	const {particle, hue} = e.content;
	const s = e.size;
	if (particle === 'bokeh') {
		return <div style={{...pos, width: s, height: s, borderRadius: '50%', background: `radial-gradient(circle, color-mix(in srgb, ${accent} 70%, #fff) 0%, transparent 70%)`}} />;
	}
	if (particle === 'confetti') {
		return <div style={{...pos, width: s, height: s * 0.45, borderRadius: 3, background: CONFETTI[Math.floor(hue * CONFETTI.length)]}} />;
	}
	if (particle === 'embers') {
		return <div style={{...pos, width: s, height: s, borderRadius: '50%', background: '#FFB347', boxShadow: `0 0 ${s}px ${s * 0.4}px rgba(255,120,30,0.65)`}} />;
	}
	return <div style={{...pos, fontSize: s, lineHeight: 1, color: hue > 0.5 ? '#FFFFFF' : accent, textShadow: `0 0 ${s * 0.6}px ${accent}`}}>✦</div>;
};

/** One pass (behind or in front of the speaker, or all in front without a cut-out) of the effects around them. */
export const AroundLayer: React.FC<{graphics: Graphic[]; t: number; plan: EditPlan; face: {x: number; y: number}; pass: Pass}> = ({graphics, t, plan, face, pass}) => {
	const {width, height} = plan.output;
	const box = faceBox(face, width, height);
	const els = graphics.flatMap((g) => passElements(aroundElements(g, t, face, width, height), pass, box));
	if (!els.length) return null;
	// Far elements first, so nearer ones overlap them.
	els.sort((a, b) => a.depth - b.depth);
	return (
		<AbsoluteFill style={{overflow: 'hidden'}}>
			{els.map((e) => (
				<ElementView key={e.key} e={e} accent={plan.style.graphics.accent_color} />
			))}
		</AbsoluteFill>
	);
};
