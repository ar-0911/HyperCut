"""The editing agent: several reels from one long recording, planned first, then made and checked (ADR 0031).

    session = run_agent("talk.mp4", "media/<id>", count=4, job_dir_for=lambda i: Path(f"media/reel-{i}"))

1. **Understand.** The recording (up to an hour) is normalized and transcribed once.
2. **Plan.** Claude reads the transcript as numbered sentences and proposes clips: each one a self-contained
   moment of 20-75 s of source that opens strong and ends on a full sentence, with a title and why it works.
   Code checks every proposal (sentence boundaries, length, no overlap). Without Claude, or if its answer is
   unusable, clips are picked by code: sentence-aligned windows spread over the recording.
   The plan is written to `agent.json` before anything is made, so the person sees what is coming.
3. **Act.** Each clip is cut out of the recording and made into a normal job with the usual pipeline (its words
   from the transcript already made, so Whisper runs once). Each reel opens in the editor like any other.
4. **Check.** The plan checks (ADR 0023) run on each reel; what code can fix is fixed (too long: end on an earlier
   sentence; a hook that starts mid-sentence: the next hook candidate; a graphic that never shows or doubles up:
   removed), up to two rounds. What is left is listed on the reel.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from hypercut import checks, edit, history, llm
from hypercut import plan as plan_mod
from hypercut.analyze.takes import sentences
from hypercut.plan import EditPlan, Transcript, Word
from hypercut.variants import rehook, trim_to

log = logging.getLogger(__name__)

AGENT_FILE = "agent.json"
MAX_REELS = 8
MIN_CLIP, MAX_CLIP = 20.0, 75.0  # seconds of source; the reel is shorter once pauses are cut
TARGET_CLIP = 45.0
MAX_REEL = 58.0  # a reel longer than this after cutting ends on an earlier sentence
FIX_ROUNDS = 2
EXCERPT_PAD = 0.3  # seconds of source kept before the first word and after the last

SYSTEM = "You are a senior short-form video editor choosing clips from a long recording. Answer with JSON only."

PROMPT = """This is the transcript of a {minutes:.0f}-minute recording, as numbered sentences with their times.
{mode_line}
Choose up to {count} clips that will each work as a short vertical video on their own:
- one complete idea a viewer gets without the rest of the recording (no "as I said", no dangling "this");
- it should open on a line that makes people stay (a claim, a surprise, a question, a number);
- {low:.0f} to {high:.0f} seconds long, ideally about {target:.0f}; whole sentences only;
- clips must not overlap; prefer the strongest moments over even coverage.

Sentences:
{sentences}

Answer as {{"clips": [{{"first": <first sentence number>, "last": <last sentence number>, "title": "<5-8 word title>",
"why": "<one sentence: why this works as a short>"}}]}}, best first."""


@dataclass
class Clip:
    start: float  # source seconds of the recording
    end: float
    title: str
    why: str = ""
    picked_by: str = "claude"  # or "code"
    job_id: str | None = None
    status: str = "planned"  # planned, making, done, failed
    error: str | None = None
    fixes: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    reel_seconds: float | None = None


def _lines(transcript: Transcript) -> list[list[Word]]:
    return [s for s in sentences(sorted(transcript.words, key=lambda w: w.start)) if s]


def _text(words: list[Word]) -> str:
    return " ".join(w.text for w in words).strip()


def _valid(clips: list[Clip], duration: float) -> list[Clip]:
    """Clips in range, not overlapping, best first as given."""
    kept: list[Clip] = []
    for c in clips:
        if not (0 <= c.start < c.end <= duration + 0.5) or not (MIN_CLIP <= c.end - c.start <= MAX_CLIP):
            continue
        if any(c.start < k.end and c.end > k.start for k in kept):
            continue
        kept.append(c)
    return kept


def propose(transcript: Transcript, duration: float, count: int, mode: str | None = None, ask=None) -> list[Clip]:
    """Claude's clips, checked. Raises llm.LLMError when Claude can't be asked; returns [] for an unusable answer."""
    lines = _lines(transcript)
    if not lines:
        return []
    listing = "\n".join(f"{i}. [{s[0].start:.1f}-{s[-1].end:.1f}] {_text(s)}" for i, s in enumerate(lines))
    mode_line = f"It is edited as: {mode.replace('_', ' ')}." if mode else ""
    prompt = PROMPT.format(minutes=duration / 60, mode_line=mode_line, count=count, low=MIN_CLIP, high=MAX_CLIP,
                           target=TARGET_CLIP, sentences=listing)
    raw = (ask or llm.ask_json)(prompt, system=SYSTEM)
    clips = []
    for item in raw.get("clips", []) if isinstance(raw, dict) else []:
        try:
            first, last = int(item["first"]), int(item["last"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= first <= last < len(lines)):
            continue
        title = str(item.get("title") or _text(lines[first])[:60]).strip()[:80]
        clips.append(Clip(start=lines[first][0].start, end=lines[last][-1].end, title=title,
                          why=str(item.get("why") or "").strip()[:300]))
    return _valid(clips, duration)[:count]


def fallback(transcript: Transcript, duration: float, count: int, taken: list[Clip] | None = None) -> list[Clip]:
    """Clips picked by code: sentence-aligned windows of about TARGET_CLIP s, spread over the recording, avoiding
    `taken`. The densest speech in each part of the recording wins."""
    lines = _lines(transcript)
    taken = list(taken or [])
    windows: list[tuple[float, Clip]] = []
    for i in range(len(lines)):
        j = i
        while j + 1 < len(lines) and lines[j + 1][-1].end - lines[i][0].start <= TARGET_CLIP:
            j += 1
        start, end = lines[i][0].start, lines[j][-1].end
        if end - start < MIN_CLIP:
            continue
        words = sum(len(s) for s in lines[i:j + 1])
        windows.append((words / (end - start), Clip(start=start, end=end, title=_text(lines[i])[:60], picked_by="code",
                                                    why="Picked by code: a stretch of steady speech.")))
    out: list[Clip] = []
    wanted = count - len(taken)
    if wanted <= 0 or not windows:
        return out
    # One per equal part of the recording, so the reels cover it.
    part = duration / wanted
    for k in range(wanted):
        lo, hi = k * part, (k + 1) * part
        best = [(d, c) for d, c in windows if lo <= c.start < hi
                and not any(c.start < t.end and c.end > t.start for t in taken + out)]
        if best:
            out.append(max(best, key=lambda x: x[0])[1])
    return out


def plan_clips(transcript: Transcript, duration: float, count: int, mode: str | None = None, ask=None) -> list[Clip]:
    count = max(1, min(count, MAX_REELS))
    try:
        clips = propose(transcript, duration, count, mode, ask)
    except llm.LLMError as e:
        log.warning("Claude could not choose clips, choosing by code: %s", e)
        clips = []
    if len(clips) < count:
        clips += fallback(transcript, duration, count, clips)
    return sorted(clips, key=lambda c: c.start)


def excerpt_words(transcript: Transcript, start: float, end: float) -> Transcript:
    """The words of [start, end) on the excerpt's own timeline (0 at `start - EXCERPT_PAD`)."""
    origin = max(0.0, start - EXCERPT_PAD)
    words = [w.model_copy(update={"start": round(w.start - origin, 3), "end": round(w.end - origin, 3)})
             for w in transcript.words if start - 1e-3 <= w.start and w.end <= end + 1e-3]
    return transcript.model_copy(update={"words": words})


def cut_excerpt(mp4: Path, start: float, end: float, out: Path) -> Path:
    """The clip as its own video file, frame-accurate (re-encoded)."""
    origin = max(0.0, start - EXCERPT_PAD)
    res = subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-ss", f"{origin:.3f}", "-i", str(mp4), "-t", f"{end + EXCERPT_PAD - origin:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        str(out),
    ], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"could not cut the clip: {res.stderr.strip()[-300:]}")
    return out


def self_check(plan: EditPlan) -> tuple[EditPlan, list[str], list[str]]:
    """Fix what code can from the plan checks, up to FIX_ROUNDS times. Returns the plan, what was fixed, and what is
    left (as messages)."""
    fixes: list[str] = []
    for _ in range(FIX_ROUNDS):
        issues = checks.check(plan)
        changed = False
        for issue in issues:
            if issue.code == "too_long" and edit.reel_duration(plan) > MAX_REEL:
                shorter = trim_to(plan, MAX_REEL)
                if shorter is not None:
                    plan, changed = shorter, True
                    fixes.append(f"Ended it on an earlier sentence ({edit.reel_duration(plan):.0f} s).")
            elif issue.code in ("hook_mid_sentence", "long_hook") and len(plan.hook.candidates) > 1:
                for i in range(len(plan.hook.candidates)):
                    if i == plan.hook.chosen:
                        continue
                    other = rehook(plan, i)
                    if not any(x.code == issue.code for x in checks.check(other)):
                        plan, changed = other, True
                        fixes.append(f"Opened on another hook: “{plan.hook.candidates[i].text[:50]}”.")
                        break
            elif issue.code in ("graphic_cut", "visuals_overlap", "visual_repeated") and issue.key:
                if any(g.id == issue.key for g in plan.graphics):
                    plan = plan.model_copy(update={"graphics": [g for g in plan.graphics if g.id != issue.key]})
                    changed = True
                    fixes.append(f"Removed {issue.key}: {issue.message[0].lower() + issue.message[1:]}")
            if changed:
                break  # check again from the top on the changed plan
        if not changed:
            break
    left = [f"{i.message}" for i in checks.check(plan) if i.severity == "fail" or i.code in ("too_long", "too_short")]
    return EditPlan.model_validate(plan.model_dump()), fixes, left


def save(session_dir: Path, state: dict) -> None:
    tmp = session_dir / (AGENT_FILE + ".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(session_dir / AGENT_FILE)


def load(session_dir: str | Path) -> dict | None:
    try:
        return json.loads((Path(session_dir) / AGENT_FILE).read_text())
    except (OSError, ValueError):
        return None


def run_agent(
    video: str | Path,
    session_dir: str | Path,
    count: int = 4,
    job_dir_for: Callable[[int], Path] | None = None,
    style_prompt: str = "",
    mode: str | None = None,
    kit: str | Path | None = None,
    strategy: str = "cold_open",
    ask=None,
    make=None,
    on_update: Callable[[dict], None] | None = None,
) -> dict:
    """Make up to `count` reels from the long recording `video`. `job_dir_for(i)` is where reel i's job goes (default
    `session_dir/reel-<i>`). `make` is the pipeline (default `hypercut.run.run_pipeline`). Returns the session state
    that is also in `agent.json`."""
    from hypercut.ingest import LONG_SECONDS, ingest
    from hypercut.transcribe import transcribe

    if make is None:
        from hypercut.run import run_pipeline as make
    session_dir = Path(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    job_dir_for = job_dir_for or (lambda i: session_dir / f"reel-{i}")
    state: dict = {"status": "running", "step": "understand", "count": count, "clips": [], "started": time.time()}
    lock = threading.Lock()

    def publish() -> None:
        with lock:
            save(session_dir, state)
        if on_update:
            on_update(state)

    publish()
    try:
        source, mp4, wav = ingest(video, session_dir, max_seconds=LONG_SECONDS)
        transcript = transcribe(wav)
        (session_dir / "transcript.json").write_text(transcript.model_dump_json(indent=2))

        state["step"] = "plan"
        publish()
        clips = plan_clips(transcript, source.duration, count, mode, ask)
        state["clips"] = [asdict(c) for c in clips]
        state["step"] = "make"
        publish()
        if not clips:
            raise RuntimeError("the recording has no stretch of speech long enough for a reel")

        for i, clip in enumerate(clips, start=1):
            entry = state["clips"][i - 1]
            job_dir = job_dir_for(i)
            entry["job_id"] = job_dir.name
            entry["status"] = "making"
            publish()
            try:
                job_dir.mkdir(parents=True, exist_ok=True)
                excerpt = cut_excerpt(mp4, clip.start, clip.end, job_dir / "upload.mp4")
                words = excerpt_words(transcript, clip.start, clip.end)
                plan = make(excerpt, job_dir, style_prompt, strategy, mode=mode, kit=kit, transcript=words)
                fixed, fixes, left = self_check(plan)
                if fixes:
                    history.commit(job_dir, fixed, "review", changes=fixes, note="The editing agent's own check")
                entry.update(status="done", fixes=fixes, issues=left, reel_seconds=round(edit.reel_duration(fixed), 1))
            except Exception as e:  # one failed reel doesn't stop the others
                log.warning("reel %d failed: %s", i, e)
                entry.update(status="failed", error=str(e)[:300])
            publish()
        state["status"] = "done" if any(c["status"] == "done" for c in state["clips"]) else "error"
        if state["status"] == "error":
            state["error"] = "no reel could be made"
    except Exception as e:
        state.update(status="error", error=str(e)[:500])
    state["step"] = "done"
    state["finished"] = time.time()
    publish()
    return state


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    ap = argparse.ArgumentParser(prog="python -m hypercut.agent", description="Several reels from one long recording.")
    ap.add_argument("video")
    ap.add_argument("out", help="session folder; reels go in reel-1, reel-2, ...")
    ap.add_argument("--count", type=int, default=4)
    ap.add_argument("--style", default="")
    ap.add_argument("--mode")
    args = ap.parse_args(argv)
    state = run_agent(args.video, args.out, args.count, style_prompt=args.style, mode=args.mode,
                      on_update=lambda s: print(f"[{s['step']}]", file=sys.stderr))
    for c in state["clips"]:
        print(f"{c['status']:7} {c['start']:7.1f}-{c['end']:7.1f}  {c['title']}  {c.get('error') or ''}")
    return 0 if state["status"] == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
