import type {EditPlan} from '@render/plan';

/** A caption to post the reel with (ADR 0030): its hook line, then a tag. The person edits it before posting. */
export function postCaption(plan: EditPlan): string {
	const hook = plan.hook.candidates[plan.hook.chosen]?.text.trim() ?? '';
	return [hook, '#shorts'].filter(Boolean).join('\n\n');
}
