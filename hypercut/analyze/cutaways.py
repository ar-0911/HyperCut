"""Cutaways over jump cuts (ADR 0614): a visual that ends just before a cut, or starts just after one, is
stretched to straddle it, the way an editor lays B-roll over a jump cut so the viewer never sees the skip.
Without this, the speaker comes back for a few frames and then jumps, which reads as a mistake.

Visuals here are anything that takes over part or all of the frame: illustrations and titles in the split
panel, imported B-roll, full-screen motion graphics. Pure, so tests can feed any plan; no Claude call.
"""

from __future__ import annotations

from hypercut.edit import VISUAL_TYPES
from hypercut.plan import EditPlan, Graphic

REACH = 0.8  # source seconds: a visual edge this close to a cut is pulled across it
COVER = 0.4  # source seconds the visual then runs past the cut, on the far side
ROOM = 0.3  # source seconds of the far piece that must still show the speaker alone (or another visual)


def jump_cuts(plan: EditPlan) -> list[tuple[float, float, float, float]]:
    """(start of the piece before, its end, start of the piece after, its end) for every forward jump cut."""
    segs = plan.segments
    return [(a.start, a.end, b.start, b.end) for a, b in zip(segs, segs[1:]) if b.start > a.end + 1e-3]


def _visuals(plan: EditPlan) -> list[Graphic]:
    return [g for g in plan.graphics if g.type in VISUAL_TYPES and g.layer != "behind"]


def _free(plan: EditPlan, g: Graphic, a: float, b: float) -> bool:
    """Whether no other visual, nor a layout span other than its own, is anywhere in source times a..b."""
    mine = lambda s: s.start < g.end and g.start < s.end  # noqa: E731
    return not any(o is not g and o.start < b and a < o.end for o in _visuals(plan)) and not any(
        s.mode != "speaker" and s.start < b and a < s.end and not mine(s) for s in plan.layout)


def _stretch_layout(plan: EditPlan, old_start: float, old_end: float, start: float, end: float) -> None:
    """Move the edge of the layout span that matched the visual's old edge to its new one."""
    for s in plan.layout:
        if s.mode == "speaker" or s.end <= old_start or s.start >= old_end:
            continue
        if abs(s.end - old_end) < 0.05 and end > s.end:
            s.end = end
        if abs(s.start - old_start) < 0.05 and start < s.start:
            s.start = start


def cover_cuts(plan: EditPlan) -> int:
    """Stretch visuals across the jump cuts next to them, in place. Returns how many were stretched."""
    moved = 0
    for g in sorted(_visuals(plan), key=lambda g: g.start):
        for a0, a1, b0, b1 in jump_cuts(plan):
            old = (g.start, g.end)
            # Ends just before the cut: run on into the next piece.
            if a1 - REACH <= g.end <= a1 + 1e-6 and g.start < a1 - 0.2 and b1 - b0 > COVER + ROOM:
                end = b0 + COVER
                if end <= plan.source.duration and _free(plan, g, b0, end):
                    g.end = round(end, 3)
            # Starts just after the cut: begin in the piece before.
            elif b0 - 1e-6 <= g.start <= b0 + REACH and g.end > b0 + 0.2 and a1 - a0 > COVER + ROOM:
                start = a1 - COVER
                if _free(plan, g, start, a1):
                    g.start = round(start, 3)
            if (g.start, g.end) != old:
                _stretch_layout(plan, *old, g.start, g.end)
                moved += 1
    plan.graphics.sort(key=lambda g: g.start)
    plan.layout.sort(key=lambda s: s.start)
    return moved
