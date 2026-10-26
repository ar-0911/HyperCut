"""Automatic checks of an edit plan, before anything is rendered (ADR 0023).

    check(plan) -> [Issue(code="word_clipped", severity="fail", at=12.3, message="…"), ...]

What an editor would catch on a first watch that code can see in the plan alone: a word clipped by a cut,
pauses the pacing should have removed, the reel ending mid-sentence or running outside 15-60 s, a hook that
starts mid-sentence, two full-frame visuals fighting for the same moment, a graphic that flashes by, the same
visual used twice, a picture whose file is missing. No Claude, no models, no rendering: cheap enough to run on
every edit in the editor, on every plan in the regression suite and in the benchmark.

Severity: "fail" is a defect the viewer will notice (fix it before export); "warn" is worth a look.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from hypercut import edit
from hypercut import plan as plan_mod
from hypercut.analyze.cuts import SENTENCE_END, is_filler
from hypercut.plan import EditPlan

MIN_REEL, MAX_REEL = 15.0, 60.0  # ADR 0002
MIN_GRAPHIC = 0.6  # seconds on screen below which a graphic flashes by
LONG_HOOK = 12.0
EPS = 1e-3


@dataclass
class Issue:
    code: str
    severity: str  # "fail" | "warn"
    message: str
    at: float | None = None  # reel seconds
    key: str | None = None  # graphic id, when it is about one


def _words_clipped(plan: EditPlan) -> list[Issue]:
    """A word that starts in a kept piece and runs past its end (or starts before it) is cut mid-sound."""
    out = []
    for p in edit.pieces(plan):
        for w in plan.transcript.words:
            mid = (w.start + w.end) / 2
            if not (p.start - EPS <= mid < p.end - EPS):
                continue
            lost = max(0.0, p.start - w.start) + max(0.0, w.end - p.end)
            # Word timings are loose by ~50 ms; only flag a real bite out of the word.
            if lost > 0.08 and lost > 0.25 * (w.end - w.start):
                at = p.reel(min(max(w.start, p.start), p.end))
                out.append(Issue("word_clipped", "fail", f"“{w.text}” is cut mid-word ({lost:.2f} s of it is missing).", round(at, 2)))
    return out


def _pauses(plan: EditPlan) -> list[Issue]:
    pacing = plan.style.pacing
    limit = pacing.max_silence + 2 * pacing.keep_pause + 0.25
    return [Issue("long_pause", "warn", f"A {b - a:.1f} s pause is still in the reel.", round(a, 2))
            for a, b in edit.pauses(plan, limit)]


def _fillers(plan: EditPlan) -> list[Issue]:
    if not plan.style.pacing.remove_fillers:
        return []
    return [Issue("filler_kept", "warn", f"The filler “{w.text}” is still in.", round(w.start, 2))
            for w in edit.reel_words(plan) if is_filler(w.text)]


def _length(plan: EditPlan) -> list[Issue]:
    d = edit.reel_duration(plan)
    if d < MIN_REEL:
        return [Issue("too_short", "warn", f"The reel is {d:.1f} s; shorts work best from {MIN_REEL:.0f} s.")]
    if d > MAX_REEL:
        return [Issue("too_long", "warn", f"The reel is {d:.1f} s; most platforms cap shorts around {MAX_REEL:.0f} s.")]
    return []


def _ending(plan: EditPlan) -> list[Issue]:
    ws = edit.reel_words(plan)
    if ws and not SENTENCE_END.search(ws[-1].text):
        return [Issue("ends_mid_sentence", "warn", f"The reel ends on “{ws[-1].text}”, mid-sentence.", round(ws[-1].end, 2))]
    return []


def _hook(plan: EditPlan) -> list[Issue]:
    hook = [s for s in plan.segments if s.reason == "hook"]
    if not hook:
        return []
    out = []
    length = sum(s.end - s.start for s in hook)
    if length > LONG_HOOK:
        out.append(Issue("long_hook", "warn", f"The hook runs {length:.1f} s; a cold open lands best under {LONG_HOOK:.0f} s.", 0.0))
    words = sorted(plan.transcript.words, key=lambda w: w.start)
    before = [w for w in words if w.end <= hook[0].start + 0.05]
    if before and not SENTENCE_END.search(before[-1].text) and hook[0].start - before[-1].end < 0.4:
        out.append(Issue("hook_mid_sentence", "warn", f"The hook starts mid-sentence, right after “{before[-1].text}”.", 0.0))
    return out


def _visuals(plan: EditPlan) -> list[Issue]:
    out = []
    shown = []
    for g in plan.graphics:
        r = edit.first_reel(plan, g.start, g.end)
        if r is None:
            out.append(Issue("graphic_cut", "warn", f"{g.id} ({g.type}) sits entirely in cut footage, so it never shows.", key=g.id))
            continue
        on = sum(b - a for p in edit.pieces(plan) if (b := min(g.end, p.end)) > (a := max(g.start, p.start)))
        on /= plan.style.pacing.speed
        if on < MIN_GRAPHIC and g.type not in ("particles",):
            out.append(Issue("graphic_flash", "warn", f"{g.id} ({g.type}) is on screen for only {on:.1f} s.", round(r[0], 2), g.id))
        if g.type in edit.VISUAL_TYPES:
            shown.append((r, g))
    shown.sort(key=lambda x: x[0][0])
    for (ra, a), (rb, b) in zip(shown, shown[1:]):
        if rb[0] < ra[1] - 0.1:
            out.append(Issue("visuals_overlap", "warn", f"{a.id} and {b.id} are both full-frame visuals at the same time.", round(rb[0], 2), b.id))
    seen: dict[tuple, str] = {}
    for _, g in shown:
        title = str(g.props.get("title") or g.props.get("text") or g.props.get("src") or "").strip().lower()
        if title:
            if (g.type, title) in seen:
                out.append(Issue("visual_repeated", "warn", f"{g.id} repeats {seen[(g.type, title)]} (“{title[:40]}”).", key=g.id))
            seen.setdefault((g.type, title), g.id)
    return out


def _files(plan: EditPlan, job_dir: Path) -> list[Issue]:
    out = []
    for g in plan.graphics:
        src = g.props.get("src")
        if g.type in ("media", "motion") and src and not (job_dir / str(src)).is_file():
            out.append(Issue("missing_file", "fail", f"{g.id} shows {src}, which is not in the project folder.", key=g.id))
    for b in plan.backgrounds:
        if b.kind == "media" and b.src and not (job_dir / b.src).is_file():
            out.append(Issue("missing_file", "fail", f"A background uses {b.src}, which is not in the project folder."))
    return out


def check(plan: EditPlan, job_dir: str | Path | None = None) -> list[Issue]:
    issues = _words_clipped(plan) + _pauses(plan) + _fillers(plan) + _length(plan) + _ending(plan) + _hook(plan) + _visuals(plan)
    if job_dir is not None:
        issues += _files(plan, Path(job_dir))
    return sorted(issues, key=lambda i: (i.severity != "fail", i.at if i.at is not None else -1))


def report(plan: EditPlan, job_dir: str | Path | None = None) -> dict:
    issues = check(plan, job_dir)
    return {"ok": not any(i.severity == "fail" for i in issues), "issues": [asdict(i) for i in issues]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hypercut.checks", description="Check an edit plan for defects.")
    ap.add_argument("plan")
    args = ap.parse_args(argv)
    path = Path(args.plan)
    result = report(plan_mod.load(path), path.parent)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
