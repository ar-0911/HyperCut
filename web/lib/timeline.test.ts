import {describe, expect, it} from 'vitest';
import type {EditPlan} from '@render/plan';
import {normalizePlan} from '@render/plan';
import {
	buildItems,
	dropOnTimeline,
	duplicateItem,
	moveItem,
	reelDuration,
	removeItem,
	removedGraphics,
	restoreGraphic,
	setLayout,
	showAs,
	snap,
	splitAt,
	trimItem,
} from './timeline';

// Cold open: source 10-12 first, then 0-8 and 9-20 (8-9 cut). Reel is 21 s.
const plan: EditPlan = normalizePlan({
	source: {path: 'n.mp4', width: 1920, height: 1080, fps: 30, duration: 20},
	segments: [
		{start: 10, end: 12, reason: 'hook'},
		{start: 0, end: 8, reason: 'body'},
		{start: 9, end: 20, reason: 'body'},
	],
	transcript: {words: [0.5, 1, 1.5, 3, 15].map((s, i) => ({text: `w${i}`, start: s, end: s + 0.4}))},
	graphics: [
		{id: 'v1', type: 'illustration', start: 2, end: 4, props: {title: 'Rocket'}},
		{id: 'g1', type: 'emoji_burst', start: 10.5, end: 11.5, props: {emoji: '🔥'}},
	],
	zooms: [{start: 5, end: 6}],
	layout: [{start: 2, end: 4, mode: 'split'}],
});

describe('buildItems', () => {
	const items = buildItems(plan);
	const byKey = Object.fromEntries(items.map((i) => [i.key, i]));

	it('places blocks in reel time on their tracks', () => {
		expect(reelDuration(plan)).toBeCloseTo(21);
		expect(byKey['g:v1']).toMatchObject({track: 'visuals', label: 'Rocket', pieces: [{from: 4, to: 6}]});
		expect(byKey['l:0'].track).toBe('layout');
		expect(byKey['z:0'].pieces[0].from).toBeCloseTo(7);
	});

	it('shows something inside the hook twice', () => {
		const p = byKey['g:g1'].pieces;
		expect(p).toHaveLength(2);
		expect(p[0].from).toBeCloseTo(0.5);
		expect(p[1].from).toBeCloseTo(11.5);
		expect(byKey['g:g1'].track).toBe('overlays');
	});

	it('lists clips and caption lines', () => {
		expect(items.filter((i) => i.track === 'video').map((i) => i.tone)).toEqual(['hook', 'clip', 'clip']);
		expect(items.filter((i) => i.track === 'captions').map((i) => i.label)).toEqual(['w0 w1 w2', 'w3', 'w4']);
	});
});

describe('edits', () => {
	it('moves a block by where you drop it in the reel', () => {
		const next = moveItem(plan, {kind: 'graphic', id: 'v1'}, {from: 4, to: 6}, 6);
		expect(next.graphics[0]).toMatchObject({start: 4, end: 6});
		expect(plan.graphics[0].start).toBe(2); // original untouched
	});

	it('trims edges and never inverts a block', () => {
		expect(trimItem(plan, {kind: 'graphic', id: 'v1'}, 'end', 1).graphics[0].end).toBe(5);
		const tiny = trimItem(plan, {kind: 'graphic', id: 'v1'}, 'start', 10).graphics[0];
		expect(tiny.end - tiny.start).toBeCloseTo(0.2);
	});

	it('removes blocks, caption lines and clips but never the last clip', () => {
		expect(removeItem(plan, {kind: 'zoom', index: 0}).zooms).toEqual([]);
		expect(removeItem(plan, {kind: 'caption', first: 0, last: 2}).transcript.words.map((w) => w.text)).toEqual(['w3', 'w4']);
		expect(removeItem(plan, {kind: 'segment', index: 0}).segments).toHaveLength(2);
		const one = {...plan, segments: [{start: 0, end: 20, reason: 'body' as const}]};
		expect(removeItem(one, {kind: 'segment', index: 0})).toBe(one);
	});

	it('splits the clip under the playhead', () => {
		const next = splitAt(plan, 5); // reel 5 = source 3 in the 0-8 clip
		expect(next.segments.map((s) => [s.start, s.end])).toEqual([
			[10, 12],
			[0, 3],
			[3, 8],
			[9, 20],
		]);
	});

	it('drops new graphics, imported media and removed blocks', () => {
		const a = dropOnTimeline(plan, {kind: 'graphic', type: 'kinetic_text'}, 4);
		expect(a.ref).toEqual({kind: 'graphic', id: 'u1'});
		expect(a.plan.graphics.at(-1)).toMatchObject({type: 'kinetic_text', start: 2, end: 4.5, props: {text: 'YOUR TEXT'}});

		const clip = {name: 'asset-0123456789ab.mp4', kind: 'video' as const, label: 'beach', duration: 3};
		const m = dropOnTimeline(plan, {kind: 'asset', asset: clip}, 4).plan.graphics.at(-1)!;
		expect(m).toMatchObject({id: 'm1', type: 'media', start: 2, end: 5, props: {src: clip.name, kind: 'video', duration: 3}});

		const without = removeItem(plan, {kind: 'graphic', id: 'v1'});
		expect(removedGraphics(without, plan).map((g) => g.id)).toEqual(['v1']);
		const back = dropOnTimeline(without, {kind: 'restore', id: 'v1'}, 13, plan).plan.graphics.at(-1)!;
		expect(back).toMatchObject({id: 'v1', start: 12, end: 14});
		expect(restoreGraphic(without, plan, 'v1').graphics.at(-1)).toMatchObject({start: 2, end: 4});
	});

	it('does not run a dropped block back into earlier source after the hook', () => {
		const a = dropOnTimeline(plan, {kind: 'graphic', type: 'kinetic_text'}, 1.5);
		expect(a.plan.graphics.at(-1)).toMatchObject({start: 11.5, end: 12});
	});

	it('duplicates right after the original', () => {
		const d = duplicateItem(plan, {kind: 'graphic', id: 'v1'});
		expect(d.plan.graphics.at(-1)).toMatchObject({id: 'u1', type: 'illustration', start: 4, end: 6});
	});

	it('switches a visual between split and full screen through the layout', () => {
		const full = showAs(plan, 'v1', 'visual');
		expect(full.layout).toEqual([{start: 2, end: 4, mode: 'visual'}]);
		expect(setLayout(plan, 3, 3.5, 'visual').layout).toEqual([
			{start: 2, end: 3, mode: 'split'},
			{start: 3, end: 3.5, mode: 'visual'},
			{start: 3.5, end: 4, mode: 'split'},
		]);
	});

	it('snaps within tolerance only', () => {
		expect(snap(4.05, [1, 4, 9], 0.1)).toBe(4);
		expect(snap(4.5, [1, 4, 9], 0.1)).toBe(4.5);
	});
});

describe('speed', () => {
	const slow: EditPlan = {...plan, style: {...plan.style, pacing: {...plan.style.pacing, speed: 0.5}}};

	it('stretches the reel and every block', () => {
		expect(reelDuration(slow)).toBeCloseTo(42);
		const items = buildItems(slow);
		const v1 = items.find((i) => i.key === 'g:v1')!;
		expect(v1.pieces[0].from).toBeCloseTo(8);
		expect(v1.pieces[0].to).toBeCloseTo(12);
	});

	it('trims in reel seconds', () => {
		expect(trimItem(slow, {kind: 'graphic', id: 'v1'}, 'end', 2).graphics[0].end).toBe(5);
	});
});
