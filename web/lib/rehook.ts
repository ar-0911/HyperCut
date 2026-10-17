import type {EditPlan, Segment} from '@render/plan';

type Range = [number, number];
const MIN_PIECE = 0.05;

/** Source ranges the body skips: the gaps between consecutive body segments. */
function bodyCuts(segments: Segment[]): Range[] {
	const body = segments.filter((s) => s.reason === 'body').sort((a, b) => a.start - b.start);
	const cuts: Range[] = [];
	for (let i = 1; i < body.length; i++) {
		if (body[i].start > body[i - 1].end) cuts.push([body[i - 1].end, body[i].start]);
	}
	return cuts;
}

function subtract([start, end]: Range, cuts: Range[]): Range[] {
	let pieces: Range[] = [[start, end]];
	for (const [cs, ce] of cuts) {
		pieces = pieces.flatMap((piece): Range[] => {
			const [a, b] = piece;
			if (ce <= a || cs >= b) return [piece];
			return [
				[a, Math.min(b, cs)],
				[Math.max(a, ce), b],
			];
		});
	}
	return pieces.filter(([a, b]) => b - a >= MIN_PIECE);
}

/**
 * Choose another hook candidate and rebuild `segments` the way hypercut.analyze.cuts.build_segments does.
 * The filler/silence cuts are recovered from the gaps already in the plan, so they stay as they were.
 */
export function chooseHook(plan: EditPlan, chosen: number, strategy = plan.hook.strategy): EditPlan {
	const hook = plan.hook.candidates[chosen];
	if (!hook) throw new Error(`no hook candidate ${chosen}`);
	const cuts = bodyCuts(plan.segments);
	const round = (n: number) => Math.round(n * 1000) / 1000;
	const make =
		(reason: Segment['reason']) =>
		([start, end]: Range): Segment => ({start: round(start), end: round(end), reason});

	const segments: Segment[] = [];
	let bodyStart = 0;
	if (strategy === 'trim') bodyStart = hook.start;
	else segments.push(...subtract([hook.start, hook.end], cuts).map(make('hook')));
	segments.push(...subtract([bodyStart, plan.source.duration], cuts).map(make('body')));
	return {...plan, hook: {...plan.hook, strategy, chosen}, segments};
}

/** Replace one transcript word's text (timings stay put). */
export function editWord(plan: EditPlan, index: number, text: string): EditPlan {
	const words = plan.transcript.words.map((w, i) => (i === index ? {...w, text} : w));
	return {...plan, transcript: {...plan.transcript, words}};
}
