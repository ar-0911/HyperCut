// Caption fonts. The latin woff2 files are committed in font-files/ (from Fontsource, OFL/Apache licensed,
// see font-files/licenses), so the preview and the render draw the same letters with no network. The list
// mirrors CAPTION_FONTS in hypercut/plan.py. Each font loads only when a plan uses it.

import {continueRender, delayRender} from './frame';
import anton from './font-files/anton-latin-400-normal.woff2';
import archivoBlack from './font-files/archivo-black-latin-400-normal.woff2';
import bangers from './font-files/bangers-latin-400-normal.woff2';
import bebasNeue from './font-files/bebas-neue-latin-400-normal.woff2';
import archivoWide from './font-files/archivo-latin-wdth-normal.woff2';
import instrumentSerif from './font-files/instrument-serif-latin-400-normal.woff2';
import inter from './font-files/inter-latin-wght-normal.woff2';
import montserrat from './font-files/montserrat-latin-wght-normal.woff2';
import oswald from './font-files/oswald-latin-wght-normal.woff2';
import permanentMarker from './font-files/permanent-marker-latin-400-normal.woff2';
import playfairDisplay from './font-files/playfair-display-latin-wght-normal.woff2';
import poppins500 from './font-files/poppins-latin-500-normal.woff2';
import poppins600 from './font-files/poppins-latin-600-normal.woff2';
import poppins700 from './font-files/poppins-latin-700-normal.woff2';
import poppins800 from './font-files/poppins-latin-800-normal.woff2';
import poppins900 from './font-files/poppins-latin-900-normal.woff2';

/** One file of a font: a static weight ('700') or a variable range ('100 900'). */
type FontFile = {url: string; weight: string; stretch?: string};
type FontDef = {name: string; files: FontFile[]; weights: string[]; feel: string; stretch?: string};

const variable = (url: string, from: number, to: number): FontFile[] => [{url, weight: `${from} ${to}`}];
const WEIGHTS = ['500', '600', '700', '800', '900'];

export const CAPTION_FONTS: FontDef[] = [
	{name: 'Montserrat', files: variable(montserrat, 100, 900), weights: WEIGHTS, feel: 'Bold and clean'},
	{name: 'Inter', files: variable(inter, 100, 900), weights: WEIGHTS, feel: 'Neutral, modern'},
	{
		name: 'Poppins',
		files: [poppins500, poppins600, poppins700, poppins800, poppins900].map((url, i) => ({url, weight: WEIGHTS[i]})),
		weights: WEIGHTS,
		feel: 'Round and friendly',
	},
	{name: 'Bebas Neue', files: [{url: bebasNeue, weight: '400'}], weights: ['400'], feel: 'Tall, all caps'},
	{name: 'Anton', files: [{url: anton, weight: '400'}], weights: ['400'], feel: 'Heavy, condensed'},
	{name: 'Oswald', files: variable(oswald, 200, 700), weights: ['500', '600', '700'], feel: 'Condensed, news'},
	{name: 'Archivo Black', files: [{url: archivoBlack, weight: '400'}], weights: ['400'], feel: 'Wide and punchy'},
	{name: 'Playfair Display', files: variable(playfairDisplay, 400, 900), weights: WEIGHTS, feel: 'Elegant serif'},
	// The editorial look of tech-explainer reels (ADR 0613): a tall serif for titles, and a wide heavy sans.
	{name: 'Instrument Serif', files: [{url: instrumentSerif, weight: '400'}], weights: ['400'], feel: 'Tall editorial serif'},
	{name: 'Archivo Expanded', files: [{url: archivoWide, weight: '100 900', stretch: '62% 125%'}], weights: WEIGHTS, feel: 'Wide and heavy', stretch: '125%'},
	{name: 'Permanent Marker', files: [{url: permanentMarker, weight: '400'}], weights: ['400'], feel: 'Handwritten'},
	{name: 'Bangers', files: [{url: bangers, weight: '400'}], weights: ['400'], feel: 'Comic'},
];

const loaded = new Map<string, string>();

/** CSS family for a caption font, loading it on first use. Unknown names are passed through as-is. */
export function captionFamily(name: string): string {
	const hit = loaded.get(name);
	if (hit) return hit;
	const def = CAPTION_FONTS.find((f) => f.name === name);
	if (!def) return name;
	const family = `HyperCut ${def.name}`; // our own name, so a system copy of the font can't stand in
	loaded.set(name, family);
	if (typeof document !== 'undefined' && typeof FontFace !== 'undefined') {
		for (const file of def.files) {
			const handle = delayRender(`Loading caption font ${def.name} ${file.weight}`);
			const face = new FontFace(family, `url(${file.url}) format('woff2')`, {weight: file.weight, ...(file.stretch ? {stretch: file.stretch} : {})});
			face
				.load()
				.then(() => document.fonts.add(face))
				.catch((e) => console.warn(`caption font ${def.name} failed to load; using the fallback`, e))
				.finally(() => continueRender(handle));
		}
	}
	return family;
}

/** CSS font-stretch a font is drawn at ('125%' for the expanded display face), or undefined. */
export function captionStretch(name: string): string | undefined {
	return CAPTION_FONTS.find((f) => f.name === name)?.stretch;
}

/** The closest weight the font has, so single-weight display fonts aren't smeared by fake bold. */
export function captionWeight(name: string, weight: number): number {
	const def = CAPTION_FONTS.find((f) => f.name === name);
	if (!def) return weight;
	const ws = def.weights.map(Number);
	return ws.reduce((best, w) => (Math.abs(w - weight) < Math.abs(best - weight) ? w : best), ws[0]);
}

const brandFonts = new Set<string>();

/** Register a brand kit's own font file (ADR 0026) under `family`, once; captions name it like any other font. */
export function loadBrandFont(family: string, url: string): void {
	if (!family || brandFonts.has(family) || typeof document === 'undefined' || typeof FontFace === 'undefined') return;
	brandFonts.add(family);
	const handle = delayRender(`Loading brand font ${family}`);
	const face = new FontFace(family, `url(${url})`);
	face
		.load()
		.then(() => document.fonts.add(face))
		.catch((e) => console.warn(`brand font ${family} failed to load; using the fallback`, e))
		.finally(() => continueRender(handle));
}
