import {describe, expect, it} from 'vitest';
import type {EditPlan} from '@render/plan';
import {chooseHook, editWord} from './rehook';

const plan = {
	source: {duration: 60},
	transcript: {language: 'en', words: [{start: 0, end: 1, text: 'hi'}, {start: 1, end: 2, text: 'there'}]},
	hook: {
		strategy: 'cold_open',
		chosen: 0,
		candidates: [
			{start: 10, end: 14, text: 'a', score: 0.9, why: ''},
			{start: 30, end: 36, text: 'b', score: 0.8, why: ''},
		],
	},
	// one cut at 20..22 is already in the body
	segments: [
		{start: 10, end: 14, reason: 'hook'},
		{start: 0, end: 20, reason: 'body'},
		{start: 22, end: 60, reason: 'body'},
	],
} as unknown as EditPlan;

describe('chooseHook', () => {
	it('cold open plays the new hook first and keeps the cuts', () => {
		const out = chooseHook(plan, 1);
		expect(out.hook.chosen).toBe(1);
		expect(out.segments).toEqual([
			{start: 30, end: 36, reason: 'hook'},
			{start: 0, end: 20, reason: 'body'},
			{start: 22, end: 60, reason: 'body'},
		]);
	});

	it('trim starts the body at the hook', () => {
		const out = chooseHook(plan, 1, 'trim');
		expect(out.hook.strategy).toBe('trim');
		expect(out.segments).toEqual([{start: 30, end: 60, reason: 'body'}]);
	});

	it('splits a hook around a cut inside it', () => {
		const withCut = {...plan, hook: {...plan.hook, candidates: [{start: 18, end: 25, text: 'c', score: 1, why: ''}]}};
		const out = chooseHook(withCut as EditPlan, 0);
		expect(out.segments.filter((s) => s.reason === 'hook')).toEqual([
			{start: 18, end: 20, reason: 'hook'},
			{start: 22, end: 25, reason: 'hook'},
		]);
	});

	it('rejects an unknown candidate and does not mutate', () => {
		expect(() => chooseHook(plan, 5)).toThrow();
		expect(plan.hook.chosen).toBe(0);
	});
});

describe('editWord', () => {
	it('changes only the text of one word', () => {
		const out = editWord(plan, 1, 'you');
		expect(out.transcript.words[1]).toEqual({start: 1, end: 2, text: 'you'});
		expect(plan.transcript.words[1].text).toBe('there');
	});
});
