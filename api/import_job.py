"""Make a pipeline output folder (e.g. from `python -m hypercut.run`) into a web job you can edit.

    python -m api.import_job <folder> [--plan plan.json]

The folder needs the edit plan and `normalized.mp4`. Files are hard-linked when possible, else copied.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from api import jobs
from hypercut import plan as plan_mod


def _link(src: Path, dst: Path) -> None:
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def import_job(folder: str | Path, plan_name: str = "plan.json") -> str:
    folder = Path(folder)
    plan_file = folder / plan_name
    video = folder / "normalized.mp4"
    for f in (plan_file, video):
        if not f.is_file():
            raise FileNotFoundError(f"{f} not found")
    plan = plan_mod.load(plan_file)  # validates before anything is created
    job_id = jobs.new_id()
    directory = jobs.job_dir(job_id)
    directory.mkdir(parents=True)
    _link(video, directory / "normalized.mp4")
    plan_mod.save(plan, directory / "plan.json")
    for name in ("transcript.json", "transcript.srt", "audio.wav"):  # audio lets the editor re-cut pauses
        if (folder / name).is_file():
            _link(folder / name, directory / name)
    jobs.write(job_id, status="done", stage="done", error=None, render=None, render_error=None,
               style=plan.style.name, hook_strategy=plan.hook.strategy, filename=folder.name, assets=[])
    return job_id


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m api.import_job", description=__doc__.splitlines()[0])
    ap.add_argument("folder")
    ap.add_argument("--plan", default="plan.json", help="plan file name inside the folder (default plan.json)")
    args = ap.parse_args(argv)
    try:
        job_id = import_job(args.folder, args.plan)
    except (FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"imported as job {job_id}: open http://localhost:3000/jobs/{job_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
