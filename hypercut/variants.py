"""Several versions of one edit (ADR 0018): other hooks, and shorter cuts that end on a full sentence.

    rehook(plan, 1)        the same edit opening on hook candidate 1 (the body's cuts and ending stay)
    trim_to(plan, 30)      the same edit, ending on the last full sentence that fits in 30 s of reel
    variants(plan)         [(label, plan), ...]: every other hook candidate, then 30 s and 45 s cuts

No Claude calls: everything is recomputed from the plan. CLI: python -m hypercut.variants plan.json --out DIR
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hypercut import edit
from hypercut import plan as plan_mod
from hypercut.analyze.cuts import SENTENCE_END, end_at, subtract
from hypercut.plan import EditPlan, Segment

LENGTHS = (30.0, 45.0)
MIN_SHORTER = 5.0  # a length variant must save at least this much to be worth making


def _body_cuts(segments: list[Segment]) -> list[tuple[float, float]]:
    body = sorted((s for s in segments if s.reason == "body"), key=lambda s: s.start)
    return [(a.end, b.start) for a, b in zip(body, body[1:]) if b.start > a.end]


def rehook(plan: EditPlan, chosen: int, strategy: str | None = None) -> EditPlan:
    """Open on another hook candidate. Filler and silence cuts are recovered from the gaps already in the plan,
    and the body still ends where it did."""
    hook = plan.hook.candidates[chosen]  # IndexError for a candidate that doesn't exist
    strategy = strategy or plan.hook.strategy
    body = [s for s in plan.segments if s.reason == "body"]
    end = max((s.end for s in body), default=plan.source.duration)
    cuts = _body_cuts(plan.segments)
    segments: list[Segment] = []
    start = 0.0
    if strategy == "trim":
        start = hook.start
    else:
        segments += [Segment(start=round(a, 3), end=round(b, 3), reason="hook") for a, b in subtract((hook.start, hook.end), cuts)]
    segments += [Segment(start=round(a, 3), end=round(b, 3), reason="body") for a, b in subtract((start, end), cuts)]
    out = plan.model_copy(deep=True)
    out.hook.chosen, out.hook.strategy, out.segments = chosen, strategy, segments
    return EditPlan.model_validate(out.model_dump())


def trim_to(plan: EditPlan, seconds: float) -> EditPlan | None:
    """End the reel on the last full sentence that fits in `seconds` of reel time. None if it is already that
    short, or no sentence ends in time."""
    if edit.reel_duration(plan) <= seconds:
        return None
    hook_end = sum(s.end - s.start for s in plan.segments if s.reason == "hook") / plan.style.pacing.speed
    best = None
    for i, w in enumerate(plan.transcript.words):
        mid = (w.start + w.end) / 2  # a word's end can sit exactly on a cut; its middle is played
        times = [t + (w.end - mid) / plan.style.pacing.speed for t in edit.to_reel(plan, mid) if t > hook_end]
        if times and max(times) <= seconds and SENTENCE_END.search(w.text):
            best = i
    if best is None:
        return None
    out = plan.model_copy(deep=True)
    out.segments = end_at(out.segments, out.transcript, best)
    return EditPlan.model_validate(out.model_dump())


def variants(plan: EditPlan, lengths: tuple[float, ...] = LENGTHS) -> list[tuple[str, EditPlan]]:
    """Every other hook candidate, then shorter cuts of this edit."""
    out: list[tuple[str, EditPlan]] = []
    for i, c in enumerate(plan.hook.candidates):
        if i != plan.hook.chosen:
            out.append((f"Hook {i + 1}: {c.text[:50]}", rehook(plan, i)))
    full = edit.reel_duration(plan)
    for seconds in lengths:
        short = trim_to(plan, seconds)
        if short is not None and full - edit.reel_duration(short) >= MIN_SHORTER:
            out.append((f"{edit.reel_duration(short):.0f} s cut", short))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hypercut.variants", description=__doc__.splitlines()[0])
    ap.add_argument("plan")
    ap.add_argument("--out", required=True, help="folder for variant-<n>.json")
    args = ap.parse_args(argv)
    folder = Path(args.out)
    folder.mkdir(parents=True, exist_ok=True)
    for n, (label, p) in enumerate(variants(plan_mod.load(args.plan)), 1):
        plan_mod.save(p, folder / f"variant-{n}.json")
        print(f"variant-{n}.json: {label} ({edit.reel_duration(p):.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
