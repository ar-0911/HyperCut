"""One suggested change for a first cut, for the editor's first steps (ADR 0029).

    suggest(plan, audio_wav) -> Suggestion(kind="shorter", label="Make it 44 s", why="…", plan=…) | None

Someone new to HyperCut gets their first cut, then one change worth trying, then export. The suggestion is made
from the plan alone, with no Claude call, so it is free and instant: a shorter cut when the reel runs long, a
close-second hook, or tighter pauses. The editor applies it as an ordinary undoable edit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hypercut import diff, edit
from hypercut.analyze.cuts import recut
from hypercut.plan import EditPlan
from hypercut.variants import rehook, trim_to

LONG = 50.0  # reel seconds above which a shorter cut is offered first
SHORTER = 45.0
CLOSE_HOOK = 0.15  # another hook candidate scoring within this of the chosen one is worth a look
TIGHT_SILENCE, TIGHT_PAUSE = 0.25, 0.1
MIN_SAVED = 1.0  # seconds a tighter cut must save to be worth suggesting


@dataclass
class Suggestion:
    kind: str  # "shorter" | "hook" | "tighter"
    label: str
    why: str
    plan: EditPlan
    changes: list[str] = field(default_factory=list)


def _shorter(plan: EditPlan) -> Suggestion | None:
    if edit.reel_duration(plan) <= LONG:
        return None
    short = trim_to(plan, SHORTER)
    if short is None:
        return None
    seconds = edit.reel_duration(short)
    return Suggestion("shorter", f"End it at {seconds:.0f} s",
                      f"The reel is {edit.reel_duration(plan):.0f} s. This ends it on the last full sentence before "
                      f"{SHORTER:.0f} s, so viewers reach the ending.", short)


def _hook(plan: EditPlan) -> Suggestion | None:
    candidates = plan.hook.candidates
    if len(candidates) < 2:
        return None
    chosen = candidates[plan.hook.chosen]
    others = [(c.score, i) for i, c in enumerate(candidates) if i != plan.hook.chosen and chosen.score - c.score <= CLOSE_HOOK]
    if not others:
        return None
    _, best = max(others)
    other = candidates[best]
    text = other.text if len(other.text) <= 60 else other.text[:57].rstrip() + "…"
    return Suggestion("hook", "Try the other hook", f"“{text}” scored almost as high as the opening line HyperCut picked. "
                      "See which grabs you first.", rehook(plan, best))


def _tighter(plan: EditPlan, audio_wav: str | None) -> Suggestion | None:
    pacing = plan.style.pacing
    if pacing.max_silence <= TIGHT_SILENCE and pacing.keep_pause <= TIGHT_PAUSE:
        return None
    tight = plan.model_copy(deep=True)
    tight.style.pacing.max_silence = min(pacing.max_silence, TIGHT_SILENCE)
    tight.style.pacing.keep_pause = min(pacing.keep_pause, TIGHT_PAUSE)
    tight = recut(tight, audio_wav)
    saved = edit.reel_duration(plan) - edit.reel_duration(tight)
    if saved < MIN_SAVED:
        return None
    return Suggestion("tighter", "Tighten the pauses", f"Cutting the gaps between sentences closer makes the reel "
                      f"{saved:.1f} s shorter and quicker, without cutting any words.", tight)


def suggest(plan: EditPlan, audio_wav: str | None = None) -> Suggestion | None:
    """The one change most worth trying on `plan`, or None when nothing stands out."""
    for make in (_shorter, _hook, lambda p: _tighter(p, audio_wav)):
        found = make(plan)
        if found is not None:
            changes = diff.explain(plan, found.plan)
            # A shorter or tighter cut removes many small pieces; the new length says it better.
            found.changes = [c for c in changes if not c.startswith("Removed ")] or changes
            return found
    return None
