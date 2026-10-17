import {describe, expect, it} from 'vitest';
import schema from '../../schema/edit_plan.schema.json';
import samplePlan from '../../schema/examples/sample_plan.json';
import {GRAPHIC_TYPES, normalizePlan} from './plan';

describe('normalizePlan', () => {
	it('fills defaults on the sample plan', () => {
		const p = normalizePlan(samplePlan);
		expect(p.output).toEqual({width: 1080, height: 1920, fps: 30});
		expect(p.style.caption.animation).toBe('pop');
		expect(p.graphics[1].anchor).toBe('auto');
		expect(p.zooms[0].scale).toBe(1.2);
		expect(p.segments[0].reason).toBe('hook');
	});

	it('keeps partial style overrides', () => {
		const p = normalizePlan({...samplePlan, style: {caption: {animation: 'bounce'}}});
		expect(p.style.caption.animation).toBe('bounce');
		expect(p.style.caption.words_per_line).toBe(3);
	});

	it('rejects plans that cannot render', () => {
		expect(() => normalizePlan({version: 1})).toThrow(/source/);
		expect(() => normalizePlan({...samplePlan, version: 2})).toThrow(/version/);
	});
});

describe('schema drift guard', () => {
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	const defs = (schema as any).$defs;
	it('renders every GraphicType the schema allows', () => {
		expect([...GRAPHIC_TYPES].sort()).toEqual([...defs.Graphic.properties.type.enum].sort());
	});
	it('knows every caption animation', () => {
		expect(defs.CaptionStyle.properties.animation.enum.sort()).toEqual(['bounce', 'karaoke', 'pop', 'typewriter']);
	});
});
