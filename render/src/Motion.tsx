// Full-screen motion graphics (ADR 0612): a few seconds where the reel cuts away from the speaker to a 3D
// scene of what is being said, lit like a product shot, while the speaker keeps talking. Claude designs each
// scene from the transcript as a small JSON description (objects, materials, how they move); this file draws
// it. Everything is a pure function of time, so renders are repeatable.

import {ThreeCanvas} from './frame-three';
import {useThree} from '@react-three/fiber';
import React, {useMemo} from 'react';
import {AbsoluteFill, interpolate} from './frame';
import * as THREE from 'three';
import {RoomEnvironment} from 'three/examples/jsm/environments/RoomEnvironment.js';
import {RoundedBoxGeometry} from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import {TextGeometry} from 'three/examples/jsm/geometries/TextGeometry.js';
import {FontLoader} from 'three/examples/jsm/loaders/FontLoader.js';
import {SVGLoader} from 'three/examples/jsm/loaders/SVGLoader.js';
import fontJson from 'three/examples/fonts/helvetiker_bold.typeface.json';

export type Vec3 = [number, number, number];
export type Finish = 'glossy' | 'metal' | 'matte' | 'glass' | 'emissive';
export type Anim =
	| {type: 'spin'; axis?: 'x' | 'y' | 'z'; speed?: number}
	| {type: 'float'; amount?: number; speed?: number}
	| {type: 'pulse'; amount?: number; bpm?: number}
	| {type: 'enter'; from?: 'below' | 'above' | 'left' | 'right' | 'front' | 'scale'; at?: number; dur?: number}
	| {type: 'grow'; axis?: 'x' | 'y' | 'z'; at?: number; dur?: number}
	| {type: 'draw'; at?: number; dur?: number}
	| {type: 'orbit'; radius?: number; speed?: number; axis?: 'x' | 'y' | 'z'}
	| {type: 'fall'; at?: number; height?: number};

export const SHAPES = [
	'sphere', 'box', 'cylinder', 'cone', 'torus', 'capsule', 'lathe', 'extrude', 'text', 'tube',
	'helix', 'globe', 'network', 'bars', 'stack', 'ring', 'grid', 'group',
] as const;
export type Shape = (typeof SHAPES)[number];

/** One thing in a scene. Which fields matter depends on `shape`; everything has defaults. */
export type SceneObject = {
	shape: Shape;
	color?: string;
	finish?: Finish;
	position?: Vec3;
	rotation?: Vec3; // degrees
	scale?: number | Vec3;
	anim?: Anim[];
	radius?: number;
	size?: Vec3 | number;
	height?: number;
	tube?: number;
	depth?: number;
	// lathe: [radius, y] pairs from bottom to top. tube: [x, y, z] points.
	profile?: [number, number][];
	points?: Vec3[];
	// extrude: an SVG path (any units; scaled to `size` wide). text: the words.
	path?: string;
	text?: string;
	// patterns
	count?: number;
	turns?: number;
	colors?: string[];
	values?: number[];
	spacing?: number;
	of?: SceneObject;
	children?: SceneObject[];
};

export type SceneSpec = {
	objects: SceneObject[];
	camera?: {distance?: number; height?: number; orbit?: number; push?: number};
	// 'light': a pale studio with a grid floor; 'dark': the same, near black. Never a flat colour.
	look?: 'light' | 'dark';
};

export type MotionColors = {accent: string; secondary: string; panel: string};

/** The two studio looks: background, floor grid lines, title colour. */
export const LOOKS = {
	light: {bg: '#E9ECF0', grid: '#C9CED6', ink: '#111216', shade: 0.22},
	dark: {bg: '#0B0B0E', grid: '#26272D', ink: '#F5F5F2', shade: 0.55},
} as const;

const MAX_MESHES = 600; // in one scene, patterns included
const unit = (x: number) => Math.min(1, Math.max(0, x));
const num = (v: unknown, d: number, lo = -1e4, hi = 1e4) => (typeof v === 'number' && Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : d);
const vec = (v: unknown, d: Vec3, lim = 20): Vec3 => (Array.isArray(v) && v.length === 3 ? [num(v[0], d[0], -lim, lim), num(v[1], d[1], -lim, lim), num(v[2], d[2], -lim, lim)] : d);
const deg = (v: Vec3): Vec3 => v.map((x) => (x * Math.PI) / 180) as Vec3;

/** A damped spring from 0 to 1: a small overshoot, then it settles. */
export function spring(x: number): number {
	if (x <= 0) return 0;
	if (x >= 1) return 1;
	return 1 - Math.exp(-6 * x) * Math.cos(9 * x);
}

/** 0 -> 1 between `at` and `at + dur` seconds, sprung. */
const sprung = (t: number, at: number, dur: number) => spring(unit((t - at) / Math.max(0.05, dur)));
/** 0 -> 1 between `at` and `at + dur`, eased out with no overshoot. */
export const eased = (t: number, at: number, dur: number) => 1 - (1 - unit((t - at) / Math.max(0.05, dur))) ** 3;

/** Deterministic pseudo-random numbers (the same plan always renders the same picture). */
export function seeded(seed: number): () => number {
	let s = seed >>> 0 || 1;
	return () => {
		s ^= s << 13;
		s ^= s >>> 17;
		s ^= s << 5;
		return ((s >>> 0) % 100000) / 100000;
	};
}

/** Points spread evenly over a unit sphere (Fibonacci lattice). */
export function spherePoints(n: number): Vec3[] {
	const out: Vec3[] = [];
	const golden = Math.PI * (3 - Math.sqrt(5));
	for (let i = 0; i < n; i++) {
		const y = 1 - (2 * (i + 0.5)) / n;
		const r = Math.sqrt(1 - y * y);
		out.push([Math.cos(golden * i) * r, y, Math.sin(golden * i) * r]);
	}
	return out;
}

/** The two strand points of each base pair of a double helix. */
export function helixPairs(n: number, height: number, radius: number, turns: number) {
	return Array.from({length: n}, (_, i) => {
		const y = -height / 2 + (height * i) / Math.max(1, n - 1);
		const a = (i / Math.max(1, n - 1)) * turns * Math.PI * 2;
		return {
			a: [Math.cos(a) * radius, y, Math.sin(a) * radius] as Vec3,
			b: [Math.cos(a + Math.PI) * radius, y, Math.sin(a + Math.PI) * radius] as Vec3,
		};
	});
}

/** A cheap continent-like mask on a unit sphere, for dotted globes. */
export function landAt(x: number, y: number, z: number): boolean {
	const v = Math.sin(x * 3.1 + 1.3) * Math.cos(y * 2.7 - 0.4) + Math.sin(z * 3.7 + y * 1.9) * 0.8 + Math.cos(x * 5.3 - z * 4.1) * 0.35;
	return v > 0.35 && Math.abs(y) < 0.9;
}

/** A heartbeat pulse (two quick beats, then rest), 0..1. */
export function beat(t: number, bpm = 72): number {
	const p = ((t * bpm) / 60) % 1;
	const bump = (c: number, w: number) => Math.exp(-(((p - c) / w) ** 2));
	return Math.max(bump(0.08, 0.05), 0.6 * bump(0.26, 0.05));
}

/** Palette names ("accent", "secondary", "panel", "white") or a CSS colour. */
export function resolveColor(c: string | undefined, colors: MotionColors, fallback: string): string {
	if (!c) return fallback;
	const named: Record<string, string> = {accent: colors.accent, secondary: colors.secondary, panel: colors.panel, white: '#F5F5F2'};
	if (named[c]) return named[c];
	return /^#[0-9a-fA-F]{3,8}$/.test(c) ? c : fallback;
}

const materials = new Map<string, THREE.Material>();
function material(color: string, finish: Finish = 'glossy'): THREE.Material {
	const key = `${color}|${finish}`;
	let m = materials.get(key);
	if (m) return m;
	if (finish === 'emissive') m = new THREE.MeshBasicMaterial({color, toneMapped: false});
	else if (finish === 'metal') m = new THREE.MeshPhysicalMaterial({color, metalness: 1, roughness: 0.26, clearcoat: 0.5});
	else if (finish === 'matte') m = new THREE.MeshPhysicalMaterial({color, roughness: 0.75, metalness: 0});
	else if (finish === 'glass') m = new THREE.MeshPhysicalMaterial({color, roughness: 0.05, transmission: 0.92, thickness: 0.6, ior: 1.45, transparent: true});
	else m = new THREE.MeshPhysicalMaterial({color, roughness: 0.22, metalness: 0.1, clearcoat: 1, clearcoatRoughness: 0.1});
	materials.set(key, m);
	return m;
}

const font = new FontLoader().parse(fontJson as never);

/** SVG path data -> extruded geometry `width` wide, centred, y up. */
function extrudePath(d: string, width: number, depth: number): THREE.BufferGeometry | null {
	try {
		const data = new SVGLoader().parse(`<svg xmlns="http://www.w3.org/2000/svg"><path d="${d.replace(/["<>]/g, '')}"/></svg>`);
		const shapes = data.paths.flatMap((p) => SVGLoader.createShapes(p));
		if (!shapes.length) return null;
		const geo = new THREE.ExtrudeGeometry(shapes, {depth: 1, bevelEnabled: true, bevelThickness: 0.08, bevelSize: 0.06, bevelSegments: 4, curveSegments: 24});
		geo.computeBoundingBox();
		const box = geo.boundingBox!;
		const k = width / Math.max(1e-6, box.max.x - box.min.x);
		geo.center();
		geo.scale(k, -k, depth / 1.16);
		return geo;
	} catch {
		return null;
	}
}

/** Geometry for a simple shape, cached by its parameters. */
const geometries = new Map<string, THREE.BufferGeometry | null>();
export function geometryFor(o: SceneObject): THREE.BufferGeometry | null {
	const key = JSON.stringify([o.shape, o.radius, o.size, o.height, o.tube, o.depth, o.profile, o.points, o.path, o.text]);
	if (geometries.has(key)) return geometries.get(key)!;
	const r = num(o.radius, 0.5, 0.005, 6);
	const h = num(o.height, 1, 0.01, 12);
	let g: THREE.BufferGeometry | null = null;
	switch (o.shape) {
		case 'sphere':
			g = new THREE.SphereGeometry(r, 48, 48);
			break;
		case 'box': {
			const s = typeof o.size === 'number' ? ([o.size, o.size, o.size] as Vec3) : vec(o.size, [1, 1, 1]);
			const [w, hh, dd] = s.map((x) => Math.max(0.01, Math.abs(x)));
			g = new RoundedBoxGeometry(w, hh, dd, 4, Math.min(w, hh, dd) * 0.08);
			break;
		}
		case 'cylinder':
			g = new THREE.CylinderGeometry(r, r, h, 64);
			break;
		case 'cone':
			g = new THREE.ConeGeometry(r, h, 64);
			break;
		case 'torus':
			g = new THREE.TorusGeometry(r, num(o.tube, r * 0.25, 0.005, 3), 32, 128);
			break;
		case 'capsule':
			g = new THREE.CapsuleGeometry(r, h, 16, 32);
			break;
		case 'lathe': {
			const pts = (o.profile ?? []).filter((p) => Array.isArray(p) && p.length === 2).slice(0, 64);
			if (pts.length >= 2) g = new THREE.LatheGeometry(pts.map(([x, y]) => new THREE.Vector2(num(x, 0, 0, 6), num(y, 0, -12, 12))), 96);
			break;
		}
		case 'extrude':
			if (o.path) g = extrudePath(String(o.path).slice(0, 4000), typeof o.size === 'number' ? num(o.size, 2, 0.1, 8) : 2, num(o.depth, 0.3, 0.02, 3));
			break;
		case 'text':
			if (o.text) {
				g = new TextGeometry(String(o.text).slice(0, 24), {font, size: typeof o.size === 'number' ? num(o.size, 0.6, 0.05, 3) : 0.6, depth: num(o.depth, 0.18, 0.01, 2), curveSegments: 8, bevelEnabled: true, bevelThickness: 0.02, bevelSize: 0.015, bevelSegments: 3});
				g.center();
			}
			break;
		case 'tube': {
			const pts = (o.points ?? []).slice(0, 64).map((p) => new THREE.Vector3(...vec(p, [0, 0, 0])));
			if (pts.length >= 2) g = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 240, num(o.radius, 0.05, 0.005, 1), 12);
			break;
		}
		default:
			g = null;
	}
	geometries.set(key, g);
	return g;
}

/** Where an object is, how it is turned and scaled at time t, and how much of it is drawn on. */
export function animate(o: SceneObject, t: number): {position: Vec3; rotation: Vec3; scale: Vec3; draw: number} {
	const p = [...vec(o.position, [0, 0, 0])] as Vec3;
	const r = [...deg(vec(o.rotation, [0, 0, 0], 400))] as Vec3;
	const s0 = typeof o.scale === 'number' ? num(o.scale, 1, 0.01, 20) : null;
	const s = (s0 !== null ? [s0, s0, s0] : vec(o.scale, [1, 1, 1])) as Vec3;
	let draw = 1;
	const axis = (a?: string) => (a === 'x' ? 0 : a === 'z' ? 2 : 1);
	for (const a of (o.anim ?? []).slice(0, 6)) {
		const at = num((a as {at?: number}).at, 0, 0, 30);
		switch (a.type) {
			case 'spin':
				r[axis(a.axis)] += t * num(a.speed, 0.6, -6, 6);
				break;
			case 'float':
				p[1] += Math.sin(t * num(a.speed, 1.4, 0, 10)) * num(a.amount, 0.08, 0, 2);
				break;
			case 'pulse': {
				const k = 1 + num(a.amount, 0.08, 0, 1) * beat(t, num(a.bpm, 72, 20, 200));
				s.forEach((_, i) => (s[i] *= k));
				break;
			}
			case 'enter': {
				const k = sprung(t, at, num(a.dur, 0.6, 0.05, 5));
				const from = a.from ?? 'below';
				if (from === 'scale') s.forEach((_, i) => (s[i] *= Math.max(0.001, k)));
				else {
					const off = ({below: [0, -4, 0], above: [0, 4, 0], left: [-4, 0, 0], right: [4, 0, 0], front: [0, 0, 6]} as Record<string, number[]>)[from] ?? [0, -4, 0];
					p.forEach((_, i) => (p[i] += off[i] * (1 - k)));
				}
				break;
			}
			case 'grow':
				s[axis(a.axis)] *= Math.max(0.001, eased(t, at, num(a.dur, 0.7, 0.05, 5)));
				break;
			case 'draw':
				draw = Math.min(draw, eased(t, at, num(a.dur, 0.8, 0.05, 5)));
				break;
			case 'orbit': {
				const ang = t * num(a.speed, 1, -8, 8);
				const rad = num(a.radius, 1, 0, 8);
				p[0] += Math.cos(ang) * rad;
				if (axis(a.axis) === 1) p[2] += Math.sin(ang) * rad;
				else p[1] += Math.sin(ang) * rad;
				break;
			}
			case 'fall': {
				const k = spring(unit((t - at) / 0.55));
				p[1] += (1 - k) * num(a.height, 5, 0, 20);
				if (t < at) s.forEach((_, i) => (s[i] = 0.001));
				break;
			}
		}
	}
	return {position: p, rotation: r, scale: s, draw};
}

type Ctx = {t: number; colors: MotionColors; budget: {left: number}};

/** One object and its children. Patterns expand into many meshes, within the scene's mesh budget. */
const Obj: React.FC<{o: SceneObject; ctx: Ctx; index?: number}> = ({o, ctx, index = 0}) => {
	if (!o || !SHAPES.includes(o.shape) || ctx.budget.left <= 0) return null;
	const {t, colors} = ctx;
	const now = animate(o, t);
	const color = resolveColor(o.color, colors, index % 2 ? colors.secondary : colors.accent);
	const kids = (o.children ?? []).slice(0, 40).map((c, i) => <Obj key={`c${i}`} o={c} ctx={ctx} index={i} />);
	let body: React.ReactNode = null;
	const geo = geometryFor(o);
	if (geo) {
		ctx.budget.left -= 1;
		// Drawn on: tubes grow along their length; text grows in place.
		if (o.shape === 'tube' && geo.index) geo.setDrawRange(0, now.draw < 1 ? Math.floor((geo.index.count * now.draw) / 3) * 3 : Infinity);
		body = <mesh geometry={geo} material={material(color, o.finish)} scale={o.shape === 'text' ? Math.max(0.001, now.draw) : 1} />;
	} else body = <Pattern o={o} ctx={ctx} color={color} />;
	return (
		<group position={now.position} rotation={now.rotation} scale={now.scale}>
			{body}
			{kids}
		</group>
	);
};

/** Shapes made of many parts: a DNA helix, a dotted globe, a network, bars, and stacks, rings or grids of a child. */
const Pattern: React.FC<{o: SceneObject; ctx: Ctx; color: string}> = ({o, ctx, color}) => {
	const {t, colors} = ctx;
	const count = Math.round(num(o.count, 12, 1, 200));
	const palette = (o.colors ?? []).slice(0, 6).map((c) => resolveColor(c, colors, color));
	const pick = (i: number) => (palette.length ? palette[i % palette.length] : i % 2 ? colors.secondary : colors.accent);
	switch (o.shape) {
		case 'helix': {
			const height = num(o.height, 6, 0.5, 14);
			const radius = num(o.radius, 0.9, 0.1, 4);
			const pairs = helixPairs(count, height, radius, num(o.turns, 2.2, 0.2, 8));
			const strandA = material(pick(0), o.finish);
			const strandB = material(pick(1), o.finish);
			const bases = ['#F4F1EA', '#9FE3D2', '#FFD27A', '#C7B8FF'].map((c) => material(c));
			const strand = (k: 'a' | 'b') => geometryFor({shape: 'tube', points: pairs.map((p) => p[k]), radius: radius * 0.09});
			const ball = geometryFor({shape: 'sphere', radius: radius * 0.15})!;
			const rung = geometryFor({shape: 'cylinder', radius: radius * 0.075, height: 1})!;
			const up = new THREE.Vector3(0, 1, 0);
			ctx.budget.left -= count * 4 + 2;
			return (
				<>
					<mesh geometry={strand('a')!} material={strandA} />
					<mesh geometry={strand('b')!} material={strandB} />
					{pairs.map((p, i) => {
						// Base pairs click into place from the middle outwards.
						const k = eased(t, 0.05 + Math.abs(i - count / 2) * 0.02, 0.4);
						const a = new THREE.Vector3(...p.a);
						const b = new THREE.Vector3(...p.b);
						const mid = a.clone().add(b).multiplyScalar(0.5);
						const q = new THREE.Quaternion().setFromUnitVectors(up, b.clone().sub(a).normalize());
						const len = (a.distanceTo(b) / 2) * Math.max(0.001, k);
						return (
							<group key={i}>
								<mesh geometry={ball} material={strandA} position={p.a} />
								<mesh geometry={ball} material={strandB} position={p.b} />
								<mesh geometry={rung} material={bases[i % 4]} position={a.clone().add(mid).multiplyScalar(0.5)} quaternion={q} scale={[1, len, 1]} />
								<mesh geometry={rung} material={bases[(i + 2) % 4]} position={b.clone().add(mid).multiplyScalar(0.5)} quaternion={q} scale={[1, len, 1]} />
							</group>
						);
					})}
				</>
			);
		}
		case 'globe':
			ctx.budget.left -= 20;
			return <GlobeDots radius={num(o.radius, 1.6, 0.2, 5)} arcs={Math.round(num(o.count, 6, 0, 16))} t={t} colors={colors} land={pick(1)} route={pick(0)} />;
		case 'network': {
			const n = Math.min(80, count);
			ctx.budget.left -= n * 2;
			return <NetworkNodes count={n} radius={num(o.radius, 1.8, 0.2, 5)} t={t} node={pick(0)} link={pick(1)} />;
		}
		case 'bars': {
			const values = (o.values ?? []).slice(0, 10).map((v) => num(v, 1, 0, 1e9));
			if (!values.length) return null;
			const max = Math.max(...values, 1e-6);
			const h = num(o.height, 3.2, 0.5, 8);
			const w = num(o.spacing, 0.75, 0.2, 3);
			ctx.budget.left -= values.length;
			const box = geometryFor({shape: 'box', size: [w * 0.7, 1, w * 0.7]})!;
			return (
				<>
					{values.map((v, i) => {
						const bh = Math.max(0.02, (v / max) * h) * Math.max(0.001, eased(t, 0.1 + i * 0.12, 0.7));
						return <mesh key={i} geometry={box} material={material(pick(i), o.finish)} position={[(i - (values.length - 1) / 2) * w, bh / 2, 0]} scale={[1, bh, 1]} />;
					})}
				</>
			);
		}
		case 'stack':
		case 'ring':
		case 'grid': {
			if (!o.of || !SHAPES.includes(o.of.shape)) return null;
			const n = Math.min(count, Math.max(0, ctx.budget.left));
			const gap = num(o.spacing, o.shape === 'stack' ? 0.15 : 0.8, 0.01, 6);
			const cols = Math.max(1, Math.round(Math.sqrt(n)));
			const ringR = num(o.radius, 1.5, 0.1, 6);
			return (
				<>
					{Array.from({length: n}, (_, i) => {
						let pos: Vec3 = [0, i * gap, 0];
						if (o.shape === 'ring') pos = [Math.cos((i / n) * Math.PI * 2) * ringR, 0, Math.sin((i / n) * Math.PI * 2) * ringR];
						else if (o.shape === 'grid') pos = [((i % cols) - (cols - 1) / 2) * gap, -(Math.floor(i / cols) - (Math.ceil(n / cols) - 1) / 2) * gap, 0];
						// Each copy starts a beat after the one before, so stacks build up and grids ripple in.
						const anim = (o.of!.anim ?? []).map((a) => (a.type === 'enter' || a.type === 'fall' || a.type === 'grow' || a.type === 'draw' ? {...a, at: num(a.at, 0, 0, 30) + i * 0.06} : a));
						const base = vec(o.of!.position, [0, 0, 0]);
						return <Obj key={i} o={{...o.of!, position: [base[0] + pos[0], base[1] + pos[1], base[2] + pos[2]], anim}} ctx={ctx} index={i} />;
					})}
				</>
			);
		}
		default:
			return null;
	}
};

const GlobeDots: React.FC<{radius: number; arcs: number; t: number; colors: MotionColors; land: string; route: string}> = ({radius, arcs, t, colors, land, route}) => {
	const parts = useMemo(() => {
		const pts = spherePoints(5200).filter(([x, y, z]) => landAt(x, y, z));
		const dots = new THREE.InstancedMesh(new THREE.SphereGeometry(radius * 0.011, 6, 6), new THREE.MeshStandardMaterial({color: '#E9EEFF', emissive: land, emissiveIntensity: 0.35}), pts.length);
		const m = new THREE.Matrix4();
		pts.forEach(([x, y, z], i) => dots.setMatrixAt(i, m.makeTranslation(x * radius, y * radius, z * radius)));
		const rnd = seeded(11);
		const pick = () => pts[Math.floor(rnd() * pts.length)];
		const lines = Array.from({length: arcs}, () => {
			const a = new THREE.Vector3(...pick()).multiplyScalar(radius * 1.005);
			const b = new THREE.Vector3(...pick()).multiplyScalar(radius * 1.005);
			const mid = a.clone().add(b).normalize().multiplyScalar(radius + a.distanceTo(b) * 0.45);
			const geo = new THREE.TubeGeometry(new THREE.QuadraticBezierCurve3(a, mid, b), 80, radius * 0.009, 6);
			return {geo, total: geo.index!.count};
		});
		return {dots, lines};
	}, [radius, arcs, land]);
	return (
		<>
			<mesh>
				<sphereGeometry args={[radius, 64, 64]} />
				<meshPhysicalMaterial color={colors.panel} roughness={0.35} metalness={0.2} clearcoat={1} />
			</mesh>
			<primitive object={parts.dots} />
			{parts.lines.map((l, i) => {
				l.geo.setDrawRange(0, Math.floor((l.total * eased(t, 0.2 + i * 0.18, 0.7)) / 3) * 3);
				return <mesh key={i} geometry={l.geo} material={material(route, 'emissive')} />;
			})}
			<mesh scale={1.08}>
				<sphereGeometry args={[radius, 48, 48]} />
				<meshBasicMaterial color={land} transparent opacity={0.1} side={THREE.BackSide} />
			</mesh>
		</>
	);
};

const NetworkNodes: React.FC<{count: number; radius: number; t: number; node: string; link: string}> = ({count, radius, t, node, link}) => {
	const parts = useMemo(() => {
		const rnd = seeded(5);
		const nodes = Array.from({length: count}, () => new THREE.Vector3(rnd() - 0.5, rnd() - 0.5, rnd() - 0.5).normalize().multiplyScalar(radius * (0.35 + rnd() * 0.65)));
		const edges: [number, number][] = [];
		nodes.forEach((a, i) => nodes.forEach((b, j) => j > i && a.distanceTo(b) < radius * 0.6 && edges.push([i, j])));
		const pos = new Float32Array(edges.length * 6);
		edges.forEach(([i, j], k) => pos.set([nodes[i].x, nodes[i].y, nodes[i].z, nodes[j].x, nodes[j].y, nodes[j].z], k * 6));
		const lines = new THREE.BufferGeometry();
		lines.setAttribute('position', new THREE.BufferAttribute(pos, 3));
		return {nodes, edges, lines};
	}, [count, radius]);
	const dot = geometryFor({shape: 'sphere', radius: radius * 0.04})!;
	const signal = geometryFor({shape: 'sphere', radius: radius * 0.018})!;
	return (
		<>
			<lineSegments geometry={parts.lines}>
				<lineBasicMaterial color={link} transparent opacity={0.5 * eased(t, 0, 0.8)} />
			</lineSegments>
			{parts.nodes.map((p, i) => (
				<mesh key={i} position={p} geometry={dot} scale={Math.max(0.001, sprung(t, i * 0.01, 0.4)) * (i % 7 === 0 ? 1.8 : 1)} material={material(i % 3 ? '#FFFFFF' : node, i % 3 ? 'glossy' : 'emissive')} />
			))}
			{parts.edges.filter((_, k) => k % 4 === 0).map(([i, j], k) => (
				<mesh key={`s${k}`} position={parts.nodes[i].clone().lerp(parts.nodes[j], (t * 0.9 + k * 0.137) % 1)} geometry={signal} material={material(node, 'emissive')} />
			))}
		</>
	);
};


/** An axis-aligned box: [min, max]. */
export type Bounds = [Vec3, Vec3];
const EMPTY: Bounds = [[Infinity, Infinity, Infinity], [-Infinity, -Infinity, -Infinity]];
const around = (c: Vec3, h: Vec3): Bounds => [[c[0] - h[0], c[1] - h[1], c[2] - h[2]], [c[0] + h[0], c[1] + h[1], c[2] + h[2]]];
const join = (a: Bounds, b: Bounds): Bounds => [a[0].map((v, i) => Math.min(v, b[0][i])) as Vec3, a[1].map((v, i) => Math.max(v, b[1][i])) as Vec3];
const isEmpty = (b: Bounds) => !(b[0][0] <= b[1][0]);

/** How big a shape is around its own origin, before its position, rotation and scale. */
function localBounds(o: SceneObject): Bounds {
	const r = num(o.radius, 0.5, 0.005, 6);
	const h = num(o.height, 1, 0.01, 12);
	const count = Math.round(num(o.count, 12, 1, 200));
	switch (o.shape) {
		case 'sphere':
			return around([0, 0, 0], [r, r, r]);
		case 'box': {
			const s = typeof o.size === 'number' ? ([o.size, o.size, o.size] as Vec3) : vec(o.size, [1, 1, 1]);
			return around([0, 0, 0], s.map((x) => Math.abs(x) / 2) as Vec3);
		}
		case 'cylinder':
		case 'cone':
			return around([0, 0, 0], [r, h / 2, r]);
		case 'capsule':
			return around([0, 0, 0], [r, h / 2 + r, r]);
		case 'torus': {
			const k = r + num(o.tube, r * 0.25, 0.005, 3);
			return around([0, 0, 0], [k, k, num(o.tube, r * 0.25, 0.005, 3)]);
		}
		case 'lathe': {
			const pts = (o.profile ?? []).filter((p) => Array.isArray(p) && p.length === 2);
			if (pts.length < 2) return EMPTY;
			const R = Math.max(...pts.map((p) => num(p[0], 0, 0, 6)));
			const ys = pts.map((p) => num(p[1], 0, -12, 12));
			return [[-R, Math.min(...ys), -R], [R, Math.max(...ys), R]];
		}
		case 'extrude': {
			const w = typeof o.size === 'number' ? num(o.size, 2, 0.1, 8) : 2;
			return around([0, 0, 0], [w / 2, w / 2, num(o.depth, 0.3, 0.02, 3) / 2]);
		}
		case 'text': {
			const size = typeof o.size === 'number' ? num(o.size, 0.6, 0.05, 3) : 0.6;
			return around([0, 0, 0], [String(o.text ?? '').slice(0, 24).length * size * 0.38, size * 0.55, num(o.depth, 0.18, 0.01, 2) / 2]);
		}
		case 'tube': {
			const pts = (o.points ?? []).slice(0, 64).map((p) => vec(p, [0, 0, 0]));
			const k = num(o.radius, 0.05, 0.005, 1);
			return pts.reduce((b, p) => join(b, around(p, [k, k, k])), EMPTY);
		}
		case 'helix': {
			const R = num(o.radius, 0.9, 0.1, 4) * 1.15;
			return around([0, 0, 0], [R, num(o.height, 6, 0.5, 14) / 2, R]);
		}
		case 'globe': {
			const R = num(o.radius, 1.6, 0.2, 5) * 1.1;
			return around([0, 0, 0], [R, R, R]);
		}
		case 'network': {
			const R = num(o.radius, 1.8, 0.2, 5);
			return around([0, 0, 0], [R, R, R]);
		}
		case 'bars': {
			const n = Math.max(1, (o.values ?? []).slice(0, 10).length);
			const w = num(o.spacing, 0.75, 0.2, 3);
			return [[-(n * w) / 2, 0, -w / 2], [(n * w) / 2, num(o.height, 3.2, 0.5, 8), w / 2]];
		}
		case 'stack':
		case 'ring':
		case 'grid': {
			if (!o.of) return EMPTY;
			const cell = boundsOf(o.of, 1);
			if (isEmpty(cell)) return EMPTY;
			const gap = num(o.spacing, o.shape === 'stack' ? 0.15 : 0.8, 0.01, 6);
			if (o.shape === 'stack') return [cell[0], [cell[1][0], cell[1][1] + (count - 1) * gap, cell[1][2]]];
			if (o.shape === 'ring') {
				const R = num(o.radius, 1.5, 0.1, 6);
				return [[cell[0][0] - R, cell[0][1], cell[0][2] - R], [cell[1][0] + R, cell[1][1], cell[1][2] + R]];
			}
			const cols = Math.max(1, Math.round(Math.sqrt(count)));
			const rows = Math.ceil(count / cols);
			const hx = ((cols - 1) / 2) * gap;
			const hy = ((rows - 1) / 2) * gap;
			return [[cell[0][0] - hx, cell[0][1] - hy, cell[0][2]], [cell[1][0] + hx, cell[1][1] + hy, cell[1][2]]];
		}
		default:
			return EMPTY;
	}
}

/**
 * Where an object ends up, in its parent's space, once its entrance is over: the box around it and its
 * children. Turned objects get the box around their bounding sphere, so it is safe whichever way they face.
 */
export function boundsOf(o: SceneObject, depth = 0): Bounds {
	if (!o || !SHAPES.includes(o.shape) || depth > 4) return EMPTY;
	const steady = {...o, anim: (o.anim ?? []).filter((a) => a.type !== 'float' && a.type !== 'orbit' && a.type !== 'spin' && a.type !== 'pulse')};
	const end = animate(steady, 1000);
	let b = localBounds(o);
	for (const c of (o.children ?? []).slice(0, 40)) b = join(b, boundsOf(c, depth + 1));
	if (isEmpty(b)) return EMPTY;
	b = [b[0].map((v, i) => Math.min(v * end.scale[i], b[1][i] * end.scale[i])) as Vec3, b[1].map((v, i) => Math.max(v * end.scale[i], b[0][i] * end.scale[i])) as Vec3];
	const spin = (o.anim ?? []).find((a) => a.type === 'spin') as {axis?: string} | undefined;
	if (spin) {
		// Spinning: the cylinder its corners sweep around the spin axis.
		const ax = spin.axis === 'x' ? 0 : spin.axis === 'z' ? 2 : 1;
		const others = [0, 1, 2].filter((i) => i !== ax);
		const R = Math.sqrt(others.reduce((acc, i) => acc + Math.max(b[0][i] ** 2, b[1][i] ** 2), 0));
		b = [b[0].map((v, i) => (i === ax ? v : -R)) as Vec3, b[1].map((v, i) => (i === ax ? v : R)) as Vec3];
	}
	if (end.rotation.some((x) => Math.abs(x) > 1e-3)) {
		// Turned: the box around its eight turned corners.
		const e = new THREE.Euler(...end.rotation);
		let r = EMPTY;
		for (const i of [0, 1]) for (const j of [0, 1]) for (const k of [0, 1]) {
			const c = new THREE.Vector3(b[i][0], b[j][1], b[k][2]).applyEuler(e);
			r = join(r, [[c.x, c.y, c.z], [c.x, c.y, c.z]]);
		}
		b = r;
	}
	b = [b[0].map((v, i) => v + end.position[i]) as Vec3, b[1].map((v, i) => v + end.position[i]) as Vec3];
	const pulse = (o.anim ?? []).find((a) => a.type === 'pulse') as {amount?: number} | undefined;
	let pad = pulse ? num(pulse.amount, 0.08, 0, 1) * Math.max(...b[1].map((v, i) => v - b[0][i])) * 0.5 : 0;
	for (const a of o.anim ?? []) {
		if (a.type === 'float') pad = Math.max(pad, num(a.amount, 0.08, 0, 2));
		if (a.type === 'orbit') pad += num(a.radius, 1, 0, 8);
	}
	return [b[0].map((v) => v - pad) as Vec3, b[1].map((v) => v + pad) as Vec3];
}

/** The part of the frame the subject should fill (camera at distance 10): under the title, above the captions. */
export const HERO = {x: [-1.45, 1.45], y: [-1.95, 1.15]} as const;

/**
 * Scale and offset that put the whole scene in the hero box, whatever sizes Claude picked. Small scenes are
 * enlarged (up to 1.6x) so the subject fills about two thirds of the frame; big ones shrink.
 */
export function fitScene(objects: SceneObject[], camera: SceneSpec['camera'], dur: number): {scale: number; offset: Vec3; floor: number} {
	const b = objects.reduce((acc, o) => join(acc, boundsOf(o)), EMPTY);
	if (isEmpty(b)) return {scale: 1, offset: [0, 0, 0], floor: HERO.y[0]};
	// The camera's closest point (after its push), so the subject still fits at the end of the shot.
	const dist = num(camera?.distance, 10, 3, 30) * (1 - num(camera?.push, 0.08, 0, 0.5));
	// An orbiting camera sees the scene's depth as width too.
	const orbits = Math.abs(num(camera?.orbit, 4, -40, 40)) * dur > 12;
	const w = Math.max(0.05, orbits ? Math.max(b[1][0] - b[0][0], b[1][2] - b[0][2]) : b[1][0] - b[0][0]);
	const h = Math.max(0.05, b[1][1] - b[0][1]);
	const d = Math.max(0.05, orbits ? Math.max(w, b[1][2] - b[0][2]) : b[1][2] - b[0][2]);
	let scale = 1;
	for (let i = 0; i < 3; i++) {
		// Things nearer the camera look bigger: size the box at the subject's front face.
		const k = Math.max(0.2, (dist - (d * scale) / 2) / 10);
		scale = Math.min(1.6, ((HERO.x[1] - HERO.x[0]) * k) / w, ((HERO.y[1] - HERO.y[0]) * k) / h);
	}
	const cx = (b[0][0] + b[1][0]) / 2;
	const cy = (b[0][1] + b[1][1]) / 2;
	const cz = (b[0][2] + b[1][2]) / 2;
	const heroY = (HERO.y[0] + HERO.y[1]) / 2;
	return {scale, offset: [-cx * scale, heroY - cy * scale, -cz * scale], floor: heroY - (h * scale) / 2};
}

/** Moves the camera each frame (the canvas only reads its `camera` prop once): a slow push and orbit. */
const CameraRig: React.FC<{t: number; dur: number; spec: SceneSpec['camera']}> = ({t, dur, spec}) => {
	const {camera} = useThree();
	const dist = num(spec?.distance, 10, 3, 30);
	const z = interpolate(t, [0, Math.max(0.1, dur)], [dist, dist * (1 - num(spec?.push, 0.08, 0, 0.5))], {extrapolateRight: 'clamp'});
	const a = ((num(spec?.orbit, 4, -40, 40) * Math.PI) / 180) * t;
	camera.position.set(Math.sin(a) * z, num(spec?.height, 0.6, -6, 8), Math.cos(a) * z);
	camera.lookAt(0, -0.4, 0);
	return null;
};

/** A soft round shadow texture, made once. */
let shadowTexture: THREE.Texture | null = null;
function softShadow(): THREE.Texture {
	if (shadowTexture) return shadowTexture;
	const size = 128;
	const data = new Uint8Array(size * size * 4);
	for (let y = 0; y < size; y++)
		for (let x = 0; x < size; x++) {
			const d = Math.hypot(x - size / 2 + 0.5, y - size / 2 + 0.5) / (size / 2);
			const a = Math.max(0, 1 - d) ** 2.2;
			data.set([0, 0, 0, Math.round(a * 255)], (y * size + x) * 4);
		}
	shadowTexture = new THREE.DataTexture(data, size, size);
	shadowTexture.needsUpdate = true;
	return shadowTexture;
}

/**
 * A studio with depth instead of a flat backdrop: a pale (or near-black) floor with a fine grid that fades
 * into the distance, soft light, real reflections from three's built-in room, and a soft contact shadow.
 */
const Studio: React.FC<{colors: MotionColors; look: 'light' | 'dark'; floor: number; width: number}> = ({colors, look, floor, width}) => {
	const {gl, scene} = useThree();
	const L = LOOKS[look];
	useMemo(() => {
		const pmrem = new THREE.PMREMGenerator(gl);
		scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
		scene.background = new THREE.Color(L.bg);
		scene.fog = new THREE.Fog(L.bg, 12, 30);
		pmrem.dispose();
	}, [gl, scene, L.bg]);
	const grid = useMemo(() => {
		const g = new THREE.GridHelper(60, 60, L.grid, L.grid);
		(g.material as THREE.Material).transparent = true;
		(g.material as THREE.Material).opacity = 0.9;
		return g;
	}, [L.grid]);
	return (
		<>
			<ambientLight intensity={look === 'light' ? 0.6 : 0.25} />
			<directionalLight position={[3, 6, 5]} intensity={look === 'light' ? 1.4 : 1.6} />
			<pointLight position={[-4, 2, -3]} intensity={look === 'light' ? 25 : 55} color={colors.accent} />
			<pointLight position={[4, -1, -2]} intensity={look === 'light' ? 20 : 40} color={colors.secondary} />
			<mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, floor - 0.02, 0]}>
				<planeGeometry args={[80, 80]} />
				<meshStandardMaterial color={L.bg} roughness={0.9} />
			</mesh>
			<primitive object={grid} position={[0, floor, 0]} />
			<mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, floor + 0.01, 0]}>
				<planeGeometry args={[width * 1.5, width * 0.7]} />
				<meshBasicMaterial map={softShadow()} transparent opacity={L.shade} depthWrite={false} />
			</mesh>
		</>
	);
};

/** The title: an editorial serif, each word coming into focus one after another; the last word in the accent. */
const Title: React.FC<{title: string; t: number; font: string; colors: MotionColors; ink: string; width: number; height: number}> = ({title, t, font: family, colors, ink, width, height}) => {
	const words = title.split(/\s+/).filter(Boolean).slice(0, 5);
	const longest = Math.min(14, Math.max(...words.map((w) => w.length), 1));
	const size = Math.min(150, (width * 0.84) / Math.max(4.5, longest * 0.5));
	return (
		<div style={{position: 'absolute', left: 0, right: 0, top: height * 0.085, textAlign: 'center', fontFamily: family, color: ink, padding: '0 7%'}}>
			<div style={{fontSize: size, fontWeight: 400, lineHeight: 1.0, letterSpacing: '-0.01em'}}>
				{words.map((w, i) => {
					const k = eased(t, 0.08 + i * 0.12, 0.45);
					return (
						<span key={i} style={{display: 'inline-block', margin: '0 0.11em', opacity: k, filter: `blur(${(1 - k) * 14}px)`, transform: `translateY(${(1 - k) * 18}px)`, color: i === words.length - 1 && words.length > 1 ? colors.accent : ink}}>
							{w}
						</span>
					);
				})}
			</div>
		</div>
	);
};

/**
 * A motion graphic filling the frame: the scene Claude designed, fitted into the frame under the title, in a
 * light or dark studio with a slow camera move. `t` is seconds since it started, `dur` its length.
 */
export const MotionGraphic: React.FC<{
	scene: SceneSpec;
	title?: string;
	t: number;
	dur: number;
	width: number;
	height: number;
	font: string;
	colors: MotionColors;
}> = ({scene, title = '', t, dur, width, height, font: family, colors}) => {
	const objects = Array.isArray(scene?.objects) ? scene.objects.slice(0, 40) : [];
	const look = scene?.look === 'dark' ? 'dark' : 'light';
	const L = LOOKS[look];
	const fit = useMemo(() => fitScene(objects, scene?.camera, dur), [objects, scene?.camera, dur]);
	const ctx: Ctx = {t, colors, budget: {left: MAX_MESHES}};
	const fade = `${L.bg}00`;
	return (
		<AbsoluteFill style={{background: L.bg}}>
			<ThreeCanvas width={width} height={height} camera={{fov: 34, position: [0, 0.6, 10], near: 0.1, far: 80}}>
				<CameraRig t={t} dur={dur} spec={scene?.camera} />
				<Studio colors={colors} look={look} floor={fit.floor} width={Math.max(1, fit.scale * 2.4)} />
				<group position={fit.offset} scale={fit.scale}>
					{objects.map((o, i) => (
						<Obj key={i} o={o} ctx={ctx} index={i} />
					))}
				</group>
			</ThreeCanvas>
			<AbsoluteFill style={{background: look === 'light' ? 'radial-gradient(ellipse at 50% 50%, transparent 60%, rgba(40,44,52,0.18) 100%)' : 'radial-gradient(ellipse at 50% 50%, transparent 55%, rgba(0,0,0,0.55) 100%)'}} />
			{title ? (
				<>
					<AbsoluteFill style={{background: `linear-gradient(180deg, ${L.bg} 0%, ${L.bg}CC 14%, ${fade} 30%)`}} />
					<Title title={title} t={t} font={family} colors={colors} ink={L.ink} width={width} height={height} />
				</>
			) : null}
		</AbsoluteFill>
	);
};
