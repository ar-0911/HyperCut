import {describe, expect, it} from 'vitest';
import type {EditPlan} from '@render/plan';
import {postCaption} from './share';

const plan = (candidates: {text: string}[], chosen = 0) => ({hook: {candidates, chosen}}) as unknown as EditPlan;

describe('postCaption', () => {
	it('leads with the chosen hook', () => {
		expect(postCaption(plan([{text: 'a'}, {text: ' Most people get this wrong. '}], 1))).toBe('Most people get this wrong.\n\n#shorts');
	});
	it('works without a hook', () => {
		expect(postCaption(plan([]))).toBe('#shorts');
	});
});
