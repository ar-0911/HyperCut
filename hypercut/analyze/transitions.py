"""Animated transitions, used sparingly (ADR 0613).

Most cuts stay as they are (`style.transitions`). A few get a designed move: the outgoing frame drops off
screen, whips sideways, pushes through or slides up while the next shot plays. They go where the picture
really changes: the cold open handing over to the body, and hard cuts between shots in the source. Nothing
here calls Claude; it needs the shot changes from reframe, so it runs once the plan is put together.

With editorial cuts (the default, ADR 0614) only the cold open gets one: J-cuts, punch-ins and a settle on new
shots join the rest, the way an editor would, and more can be added in the editor or the AI box.
"""

from __future__ import annotations

from hypercut.plan import CutKind, CutTransition, EditPlan

PER_MIN = 3  # at most this many per minute of output, about one every 20 s
MIN_GAP = 12.0  # output seconds between two transitions
EDGE = 2.0  # output seconds at the start and end of the reel that never get one
CLEAR = 0.6  # source seconds after a shot change that must show the speaker alone
# The cold open hands over with the speaker dropping off screen; later ones vary, never the same twice in a row.
ORDER: tuple[CutKind, ...] = ("whip", "zoom", "push", "drop")
LENGTH: dict[str, float] = {"drop": 0.6, "whip": 0.4, "zoom": 0.45, "push": 0.5}


def _out_time(plan: EditPlan, t: float) -> float | None:
    """Output seconds where source time t plays (its first showing), or None if it is cut."""
    pos = 0.0
    for seg in plan.segments:
        if seg.start - 1e-6 <= t < seg.end:
            return (pos + t - seg.start) / plan.style.pacing.speed
        pos += seg.end - seg.start
    return None


def _busy(plan: EditPlan, a: float, b: float) -> bool:
    """Whether a split or full-screen visual is on screen anywhere in source times a..b."""
    return any(s.mode != "speaker" and s.start < b and a < s.end for s in plan.layout) or any(
        g.type == "motion" and g.start < b and a < g.end for g in plan.graphics
    )


def candidates(plan: EditPlan) -> list[tuple[int, float]]:
    """(priority, source time) of the places a transition could go, most fitting first."""
    found: list[tuple[int, float]] = []
    segs = plan.segments
    # The cold open ending and the story starting.
    if len(segs) > 1 and segs[0].reason == "hook":
        body = next((s for s in segs[1:] if s.reason == "body"), None)
        if body is not None:
            found.append((0, body.start))
    # A new shot in the source, well inside a kept piece (a cut at a piece's edge is a jump cut already).
    for t in plan.reframe.shots:
        if any(s.start + 0.3 < t < s.end - 0.3 for s in segs):
            found.append((1, t))
    return sorted(found)


def plan_transitions(plan: EditPlan) -> list[CutTransition]:
    """Pick a few transitions, spaced out, in kinds that vary. Pure, so tests can feed any plan."""
    if not plan.segments:
        return []
    total = plan.output_duration()
    limit = max(1, int(PER_MIN * total / 60))
    places = candidates(plan)
    if plan.style.transitions.style == "editorial":
        places = [p for p in places if p[0] == 0]
    hook_end = places[0][1] if places and places[0][0] == 0 else None
    chosen: list[tuple[float, float]] = []  # (output time, source time)
    for _, t in places:
        out = _out_time(plan, t)
        if out is None or out < EDGE or out > total - EDGE:
            continue
        # The frame going out is held whole (graphics and captions too), whatever its layout. The incoming
        # graphics stay put while the footage moves, so a shot change must land on the speaker alone; the cold
        # open drops away and may uncover any layout.
        if t != hook_end and _busy(plan, t, t + CLEAR):
            continue
        if any(abs(out - o) < MIN_GAP for o, _ in chosen):
            continue
        chosen.append((out, t))
        if len(chosen) >= limit:
            break
    chosen.sort()
    cuts: list[CutTransition] = []
    turn = 0
    for _, t in chosen:
        if t == hook_end:
            kind: CutKind = "drop"
        else:
            kind = ORDER[turn % len(ORDER)]
            if cuts and cuts[-1].kind == kind:
                turn += 1
                kind = ORDER[turn % len(ORDER)]
            turn += 1
        cuts.append(CutTransition(at=round(t, 3), kind=kind, length=LENGTH[kind]))
    return cuts
