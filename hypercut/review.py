"""Claude looks at the rendered reel and fixes what a person would catch (ADR 0019).

    review(plan, "media/<job>/output.mp4") -> ReviewResult(issues, plan, changes)

Frames are sampled from the render (the middle of every graphic's first showing, plus a frame every few
seconds), each listed with what the plan has on screen there. Claude checks them for what goes wrong in an
automatic edit: a graphic over the speaker's face, text that is cut off or unreadable, a visual that doesn't
match the words, two things fighting for the same space, an awkward empty frame. It answers with issues and,
where it can, the editor assistant's operations to fix them; those are applied to a copy of the plan with the
assistant's own validation. Nothing is saved. CLI:

    python -m hypercut.review JOB_DIR [--apply]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from hypercut import edit, llm
from hypercut import plan as plan_mod
from hypercut.plan import EditPlan

MAX_FRAMES = 16
EVERY = 4.0  # seconds of reel between plain samples
FRAME_WIDTH = 540
REVIEW_OPS = ("delete", "move", "edit", "set_layout", "anchor", "remove_captions")

SYSTEM = "You are a senior short-form video editor doing a final quality check. Answer with JSON only."

PROMPT = """These are frames from an automatically edited vertical short (1080x1920, shown smaller). The reel is \
{duration:.1f} s long.

Frames, by number (reel second, layout, what the edit plan has on screen):
{frames}

Check every frame for what a professional editor would fix before publishing:
- a graphic, picture or text covering the speaker's face or mouth
- text cut off at the frame edge, overlapping other text or the captions, or too small to read on a phone
- a picture, clip or drawing that doesn't show what is being said, looks cheap, or shows a watermark or logo
- two things fighting for the same space; a visual that ends or starts at an awkward moment
- an empty or broken-looking frame (black, a missing picture, a frozen glitch)
Ignore matters of taste. Only report what you can see.

For each problem give the editor's operations that fix it, in reel seconds, from this list:
- {{"op": "delete", "keys": ["g1"]}}  remove a graphic
- {{"op": "move", "key": "g1", "start": s, "end": e}}  retime a graphic
- {{"op": "edit", "key": "g1", "props": {{"text": "..."}}}}  shorten or fix its words
- {{"op": "anchor", "key": "g1", "anchor": "top" | "center" | "bottom"}}  move a graphic up or down
- {{"op": "set_layout", "start": s, "end": e, "mode": "speaker" | "split" | "visual"}}
- {{"op": "remove_captions", "start": s, "end": e}}
Keys are the ids listed with each frame. Leave "ops" empty when the fix needs a person (e.g. a better picture).

Return {{"issues": [{{"frame": <number>, "severity": "high" | "low", "problem": "<one sentence>", "ops": [...]}}], \
"summary": "<one sentence on the overall edit>"}}"""


@dataclass
class Issue:
    at: float  # reel seconds
    severity: str
    problem: str
    ops: list = field(default_factory=list)


@dataclass
class ReviewResult:
    issues: list[Issue]
    summary: str
    plan: EditPlan
    changes: list[str]


def sample_times(plan: EditPlan) -> list[float]:
    """Reel seconds to look at: the middle of each graphic's first showing, then evenly spaced fill-ins."""
    duration = edit.reel_duration(plan)
    times = []
    for g in plan.graphics:
        span = edit.first_reel(plan, g.start, g.end)
        if span:
            times.append(round((span[0] + span[1]) / 2, 2))
    t = EVERY / 2
    while t < duration:
        if all(abs(t - x) > EVERY / 2 for x in times):
            times.append(round(t, 2))
        t += EVERY
    times = sorted(set(x for x in times if 0 <= x < duration))
    if len(times) > MAX_FRAMES:  # keep an even spread
        step = len(times) / MAX_FRAMES
        times = [times[int(i * step)] for i in range(MAX_FRAMES)]
    return times


def on_screen(plan: EditPlan, reel_t: float) -> str:
    t, _ = edit.to_source(plan, reel_t)
    mode = next((s.mode for s in plan.layout if s.start <= t < s.end), "speaker")
    items = []
    for g in plan.graphics:
        if g.start <= t < g.end:
            detail = {k: g.props[k] for k in ("text", "title", "value", "label", "items", "headline", "idea") if k in g.props}
            items.append(f"{g.id} {g.type}" + (f" {json.dumps(detail, ensure_ascii=False)[:120]}" if detail else ""))
    said = " ".join(w.text for w in plan.transcript.words if t - 1.5 <= w.start <= t + 1.5)
    return f"{mode}; {', '.join(items) or 'no graphics'}; said: \"{said}\""


def grab_frames(video: Path, times: list[float], out_dir: Path) -> list[Path]:
    frames = []
    for i, t in enumerate(times):
        out = out_dir / f"frame-{i:02d}.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
             "-vf", f"scale={FRAME_WIDTH}:-2", "-q:v", "4", str(out)],
            capture_output=True,
        )
        if not out.is_file():
            raise RuntimeError(f"could not read a frame at {t:.1f}s from {video.name}")
        frames.append(out)
    return frames


def review(plan: EditPlan, video: str | Path, ask=None, frames: list[Path] | None = None) -> ReviewResult:
    """Look at the render of `plan` and propose fixes. `frames` (with matching `sample_times`) skips ffmpeg."""
    from hypercut import assistant

    times = sample_times(plan)
    ask = ask or llm.ask_json
    with tempfile.TemporaryDirectory(prefix="hypercut-review-") as tmp:
        shots = frames if frames is not None else grab_frames(Path(video), times, Path(tmp))
        listing = "\n".join(f"{i}: {t:.1f}s, {on_screen(plan, t)}" for i, t in enumerate(times))
        raw = ask(PROMPT.format(duration=edit.reel_duration(plan), frames=listing), system=SYSTEM, images=shots, timeout=600)
    issues: list[Issue] = []
    ops: list = []
    for item in raw.get("issues") or [] if isinstance(raw, dict) else []:
        if not isinstance(item, dict) or not str(item.get("problem") or "").strip():
            continue
        frame = item.get("frame")
        at = times[frame] if isinstance(frame, int) and 0 <= frame < len(times) else 0.0
        fix = [o for o in item.get("ops") or [] if isinstance(o, dict) and o.get("op") in REVIEW_OPS]
        issues.append(Issue(at, "high" if item.get("severity") == "high" else "low", str(item["problem"])[:300], fix))
        ops += fix
    fixed, changes = assistant.apply_ops(plan, ops, 0.0, [], draw=lambda briefs: [None] * len(briefs),
                                         draw_icons=lambda items, *a, **k: [None] * len(items))
    summary = str(raw.get("summary") or "")[:300] if isinstance(raw, dict) else ""
    return ReviewResult(issues, summary, fixed, changes)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hypercut.review", description=__doc__.splitlines()[0])
    ap.add_argument("job_dir")
    ap.add_argument("--video", default="output.mp4")
    ap.add_argument("--apply", action="store_true", help="write the fixed plan back to plan.json")
    args = ap.parse_args(argv)
    job = Path(args.job_dir)
    result = review(plan_mod.load(job / "plan.json"), job / args.video)
    print(result.summary)
    for i in result.issues:
        print(f"  {i.at:5.1f}s [{i.severity}] {i.problem}" + (" (fixable)" if i.ops else ""))
    for c in result.changes:
        print("  -", c)
    if args.apply:
        plan_mod.save(result.plan, job / "plan.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
