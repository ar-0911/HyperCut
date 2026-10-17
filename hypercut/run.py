"""python -m hypercut.run VIDEO [--style 'prompt'] [--strategy trim] [--out DIR] [--render]

Runs the whole pipeline on one file without the server: ingest -> (transcribe, reframe) -> style
-> analyze, then writes plan.json (and output.mp4 with --render). The API calls `run_pipeline` too.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from hypercut import plan as plan_mod
from hypercut.analyze import analyze
from hypercut.ingest import ingest
from hypercut.plan import EditPlan
from hypercut.reframe import reframe
from hypercut.style import style_from_prompt
from hypercut.transcribe import transcribe

ROOT = Path(__file__).resolve().parent.parent
RENDER_DIR = ROOT / "render"


def run_pipeline(
    video: str | Path,
    job_dir: str | Path,
    style_prompt: str = "",
    strategy: str = "cold_open",
    on_stage: Callable[[str], None] | None = None,
) -> EditPlan:
    """Run every stage and save `plan.json` in `job_dir`. `on_stage(name)` is called as each begins."""
    job_dir = Path(job_dir)
    note = on_stage or (lambda _name: None)

    note("ingest")
    source, mp4, wav = ingest(video, job_dir)

    note("transcribe")
    # Face tracking needs only the video, so it runs while Whisper works on the audio.
    with ThreadPoolExecutor(max_workers=1) as pool:
        track = pool.submit(reframe, str(mp4), source)
        transcript = transcribe(wav)
        reframe_result = track.result()

    note("style")
    style = style_from_prompt(style_prompt)

    note("analyze")
    plan = analyze(transcript, source, style, audio_wav=str(wav), strategy=strategy)
    plan = plan.model_copy(update={"reframe": reframe_result})
    plan = EditPlan.model_validate(plan.model_dump())  # fail here, not in the renderer
    plan_mod.save(plan, job_dir / "plan.json")
    return plan


def render_plan(job_dir: str | Path, out_name: str = "output.mp4", render_dir: Path = RENDER_DIR) -> Path:
    """Render `plan.json` + `normalized.mp4` in `job_dir` with the Remotion project's npm script."""
    job_dir = Path(job_dir).resolve()
    out = job_dir / out_name
    cmd = [
        "npm", "run", "render", "--",
        "--plan", str(job_dir / "plan.json"),
        "--video", str(job_dir / "normalized.mp4"),
        "--out", str(out),
    ]
    res = subprocess.run(cmd, cwd=render_dir, capture_output=True, text=True)
    if res.returncode != 0 or not out.is_file():
        raise RuntimeError("render failed: " + (res.stderr or res.stdout).strip()[-2000:])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hypercut.run", description=__doc__.splitlines()[0])
    ap.add_argument("video")
    ap.add_argument("--style", default="", help="style prompt, e.g. 'calm minimal, white captions'")
    ap.add_argument("--strategy", choices=["cold_open", "trim"], default="cold_open")
    ap.add_argument("--out", help="output directory (default media/cli-<video name>)")
    ap.add_argument("--render", action="store_true", help="also render output.mp4 with Remotion")
    args = ap.parse_args(argv)

    job_dir = Path(args.out) if args.out else ROOT / "media" / ("cli-" + Path(args.video).stem)
    try:
        plan = run_pipeline(
            args.video, job_dir, args.style, args.strategy,
            on_stage=lambda s: print("[" + s + "]", file=sys.stderr),
        )
        print(
            f"{len(plan.transcript.words)} words, {len(plan.hook.candidates)} hooks, "
            f"{len(plan.graphics)} graphics, {len(plan.zooms)} zooms -> {job_dir / 'plan.json'}"
        )
        if args.render:
            print(f"rendered {render_plan(job_dir)}")
    except Exception as e:  # stage errors carry user-safe messages
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
