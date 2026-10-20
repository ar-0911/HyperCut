"""python -m hypercut.run VIDEO [--style 'prompt'] [--strategy trim] [--out DIR] [--render]

Runs the whole pipeline on one file without the server: ingest -> (transcribe, reframe) -> style
-> analyze (with per-beat layouts and illustrations unless --no-visuals) [-> matte, when the style asks
for green-screen effects], then writes plan.json (and output.mp4 with --render). The API calls
`run_pipeline` too.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from hypercut import plan as plan_mod
from hypercut.analyze import analyze
from hypercut.analyze.transitions import plan_transitions
from hypercut.generate import generate, pending
from hypercut.ingest import ingest
from hypercut.matte import MATTE_FILE, matte, needs_matte, place_titles
from hypercut.plan import EditPlan, Style
from hypercut.reframe import reframe
from hypercut.style import style_from_prompt
from hypercut.transcribe import transcribe

ROOT = Path(__file__).resolve().parent.parent
RENDER_DIR = ROOT / "render"

log = logging.getLogger(__name__)


def run_pipeline(
    video: str | Path,
    job_dir: str | Path,
    style_prompt: str = "",
    strategy: str = "cold_open",
    on_stage: Callable[[str], None] | None = None,
    visuals: bool = True,
    recipe: Style | None = None,
    pictures: bool = False,
) -> EditPlan:
    """Run every stage and save `plan.json` in `job_dir`. `on_stage(name)` is called as each begins.
    A `recipe` (a saved style, ADR 0018) is used as the style as it is, instead of reading the style prompt.
    `pictures` lets some visuals be stock footage or generated pictures / clips (ADR 0020): off by default, and
    without keys it changes nothing."""
    job_dir = Path(job_dir)
    note = on_stage or (lambda _name: None)

    note("ingest")
    source, mp4, wav = ingest(video, job_dir)

    note("transcribe")
    # Face tracking needs only the video and the style only the prompt, so both run while Whisper works.
    with ThreadPoolExecutor(max_workers=3) as pool:
        track = pool.submit(reframe, str(mp4), source)
        styled = pool.submit(lambda: recipe.model_copy(deep=True)) if recipe is not None else pool.submit(style_from_prompt, style_prompt)
        transcript = transcribe(wav)
        reframe_result = track.result()

        note("style")
        style = styled.result()
        # The speaker is cut out only when the style prompt asked for a different background or things behind
        # them (ADR 0901, 0614): the cut-out is made while Claude plans the edit.
        cutout = None
        if style.depth.enabled and style.depth.cutout:
            cutout = pool.submit(matte, mp4, source, reframe_result, job_dir / MATTE_FILE)

        note("analyze")
        plan = analyze(transcript, source, style, audio_wav=str(wav), strategy=strategy, visuals=visuals,
                       pictures=pictures)
        if cutout is not None:
            note("matte")
            try:
                cutout.result()
            except Exception as e:  # the reel still renders, just without the cut-out effects
                log.warning("speaker cut-out failed, rendering without green-screen effects: %s", e)
                cutout = None
    plan = plan.model_copy(update={"reframe": reframe_result})
    # Stock footage and generated pictures / clips the plan asks for (ADR 0016); none unless asked for and keys are set.
    if pending(plan):
        note("generate")
        generate(plan, job_dir)
    # A few animated transitions at the shot changes face tracking found (ADR 0613).
    plan.cuts = plan_transitions(plan)
    if cutout is not None:
        place_titles(plan, job_dir / MATTE_FILE)
    plan = EditPlan.model_validate(plan.model_dump())  # fail here, not in the renderer
    plan_mod.save(plan, job_dir / "plan.json")
    return plan


_matte_lock = threading.Lock()  # one cut-out at a time: the editor and a render may both ask


def ensure_matte(job_dir: str | Path, force: bool = False) -> Path | None:
    """Make the speaker cut-out for the job if its plan asks for green-screen effects (or `force`, when
    the editor has turned them on in an unsaved plan) and there is none yet. Returns its path, or None
    if not needed."""
    job_dir = Path(job_dir)
    plan = plan_mod.load(job_dir / "plan.json")
    if not (force or needs_matte(plan)):
        return None
    out = job_dir / MATTE_FILE
    with _matte_lock:
        if not out.is_file():
            matte(job_dir / "normalized.mp4", plan.source, plan.reframe, out)
    return out


def place_new_titles(job_dir: str | Path) -> None:
    """Give titles put behind the speaker in the editor their height from the cut-out, before a render."""
    job_dir = Path(job_dir)
    path, out = job_dir / "plan.json", job_dir / MATTE_FILE
    plan = plan_mod.load(path)
    unplaced = any(g.layer == "behind" and g.type == "kinetic_text" and "y" not in g.props for g in plan.graphics)
    if needs_matte(plan) and out.is_file() and unplaced:
        plan_mod.save(place_titles(plan, out), path)


def draw_new_around(job_dir: str | Path, draw=None, illustrate=None, design=None) -> None:
    """Draw the graphics added or changed in the editor before a render: orbit / fly-out items (ADR 0610),
    cards and scenes (ADR 0611), motion graphics (ADR 0612)."""
    from hypercut.analyze.analyze import draw_around
    from hypercut.analyze.stage import draw_stage

    from hypercut.analyze.motion import design_scenes

    path = Path(job_dir) / "plan.json"
    plan = plan_mod.load(path)
    # Motion graphics added in the editor (or whose idea was changed) get their 3D scene designed (ADR 0612).
    scenes = design_scenes(plan.graphics, plan.transcript, plan.style, design)
    # Cards are drawn whatever the depth settings: without the cut-out they play over the real footage (ADR 0614).
    icons = draw_around(plan.graphics, plan.style, draw) if plan.style.depth.enabled else False
    if draw_stage(plan.graphics, plan.style, illustrate) or icons or scenes:
        plan_mod.save(plan, path)


def fetch_new_assets(job_dir: str | Path) -> None:
    """Fetch the pictures and clips added or asked again for in the editor, before a render (ADR 0016)."""
    path = Path(job_dir) / "plan.json"
    plan = plan_mod.load(path)
    if pending(plan):
        plan_mod.save(generate(plan, job_dir), path)


def render_plan(job_dir: str | Path, out_name: str = "output.mp4", render_dir: Path = RENDER_DIR,
                extra_args: list[str] | None = None) -> Path:
    """Render `plan.json` + `normalized.mp4` in `job_dir` with the Remotion project's npm script.
    A `matte.webm` next to the video is picked up by the render script."""
    job_dir = Path(job_dir).resolve()
    try:
        ensure_matte(job_dir)
        place_new_titles(job_dir)
    except Exception as e:
        log.warning("speaker cut-out failed, rendering without green-screen effects: %s", e)
    try:
        draw_new_around(job_dir)
    except Exception as e:
        log.warning("drawing effects around the speaker failed, rendering built-in icons: %s", e)
    try:
        fetch_new_assets(job_dir)
    except Exception as e:
        log.warning("fetching generated pictures failed, rendering without them: %s", e)
    out = job_dir / out_name
    cmd = [
        "npm", "run", "render", "--",
        "--plan", str(job_dir / "plan.json"),
        "--video", str(job_dir / "normalized.mp4"),
        "--out", str(out),
        *(extra_args or []),
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
    ap.add_argument("--no-visuals", action="store_true", help="skip per-beat layouts and illustrations")
    ap.add_argument("--pictures", action="store_true",
                    help="let some visuals be stock footage or generated pictures (needs keys, see .env.example)")
    args = ap.parse_args(argv)

    job_dir = Path(args.out) if args.out else ROOT / "media" / ("cli-" + Path(args.video).stem)
    try:
        plan = run_pipeline(
            args.video, job_dir, args.style, args.strategy,
            on_stage=lambda s: print("[" + s + "]", file=sys.stderr),
            visuals=not args.no_visuals, pictures=args.pictures,
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
