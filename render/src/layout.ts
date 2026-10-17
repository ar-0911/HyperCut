// Pure geometry: reframe interpolation, crop rectangle, zoom curve, graphic placement.

import type {Anchor, ReframeKey, Zoom} from './plan';

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** Crop center at source time t: linear between keys, held at the ends, 0.5/0.5 with no keys. */
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
