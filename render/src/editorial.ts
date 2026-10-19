// Editorial cuts (ADR 0614): how a human editor joins talking-head pieces, as pure functions of the plan.
//
// - J-cut: at a jump cut the outgoing picture holds a few frames while the next piece's sound has already
//   started. The kept pause before the next word means the lips never go out of sync; the ear leads the eye,
//   which is what makes a cut feel smooth.
// - Punch-in: consecutive pieces of the same shot alternate between the normal framing and a tighter one, so
//   a jump cut reads as a deliberate camera change instead of a skip.
// - Settle: where the shot itself changes (a hard cut in the source, or a jump to another shot) the new shot
//   eases in from slightly closer, a small push that carries the eye across the cut.

import type {EditPlan} from './plan';
import type {Timeline} from './timing';

/** Output frames the outgoing picture holds past its end while the next piece's sound plays. */
export const JCUT_FRAMES = 4;
/** The tighter framing of every other piece of the same shot. */
export const PUNCH_IN = 1.12;
/** How much closer a new shot starts, and over how many seconds it settles back. */
export const SETTLE = {scale: 1.04, seconds: 0.4};
const EPS = 0.05; // source seconds: a shot change this close to a cut counts as at the cut

const easeOut = (x: number) => 1 - (1 - x) ** 3;
const shotsBetween = (plan: EditPlan, a: number, b: number) => plan.reframe.shots.some((s) => s >= a - EPS && s <= b + EPS);

export const isEditorial = (plan: EditPlan) => plan.style.transitions.style === 'editorial';

/** Whether piece i+1 starts somewhere else in the source than piece i ends (a jump cut, not a split). */
export function isJumpCut(tl: Timeline, i: number): boolean {
	const seg = tl.segments[i];
	const next = tl.segments[i + 1];
	return Boolean(next) && Math.abs(next.start - seg.end) > 1e-3;
}

/** Whether the jump cut after piece i stays in the same shot: forward in the source, no shot change across it. */
export function sameShot(plan: EditPlan, tl: Timeline, i: number): boolean {
	const seg = tl.segments[i];
	const next = tl.segments[i + 1];
	return isJumpCut(tl, i) && next.start > seg.end && !shotsBetween(plan, seg.end, next.start);
}

/** Per piece: true where it is framed tighter. Alternates across same-shot jump cuts, resets on a new shot. */
export function punchedIn(plan: EditPlan, tl: Timeline): boolean[] {
	const out: boolean[] = [];
	tl.segments.forEach((_, i) => {
		out.push(i > 0 && sameShot(plan, tl, i - 1) ? !out[i - 1] : i > 0 && !isJumpCut(tl, i - 1) ? out[i - 1] : false);
	});
	return out;
}

/** Source time the current shot started at, within piece i, if it started there (else null). */
function shotStart(plan: EditPlan, tl: Timeline, i: number, t: number): number | null {
	const seg = tl.segments[i];
	const inside = plan.reframe.shots.filter((s) => s > seg.start + EPS && s <= t);
	if (inside.length) return inside[inside.length - 1];
	return i > 0 && isJumpCut(tl, i - 1) && !sameShot(plan, tl, i - 1) ? seg.start : null;
}

/** Extra scale (about the face) for piece i at source time t: its punch-in times the settle of a new shot. */
export function editorialScale(plan: EditPlan, tl: Timeline, i: number, t: number, punched: boolean[]): number {
	if (!isEditorial(plan)) return 1;
	const s = shotStart(plan, tl, i, t);
	const k = s === null ? 1 : Math.min(1, Math.max(0, (t - s) / tl.speed / SETTLE.seconds));
	return (punched[i] ? PUNCH_IN : 1) * (1 + (SETTLE.scale - 1) * (1 - easeOut(k)));
}

/** J-cut frames after piece i: the outgoing picture held under the next piece's sound, or 0 where it can't be. */
export function jcutFrames(plan: EditPlan, tl: Timeline, i: number): number {
	const seg = tl.segments[i];
	const next = tl.segments[i + 1];
	if (!isEditorial(plan) || !isJumpCut(tl, i) || next.frames <= JCUT_FRAMES + 1) return 0;
	// An animated transition already covers this cut.
	if (plan.cuts.some((c) => Math.abs(c.at - next.start) < 1e-3)) return 0;
	const holds = (JCUT_FRAMES / tl.fps) * tl.speed; // source seconds the outgoing picture runs on
	// Only frames that exist and belong to the same shot: running into the next shot would flash it.
	if (seg.end + holds > plan.source.duration || plan.reframe.shots.some((s) => s > seg.end - EPS && s <= seg.end + holds + EPS)) return 0;
	return JCUT_FRAMES;
}
