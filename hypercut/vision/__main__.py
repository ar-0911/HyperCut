"""python -m hypercut.vision JOB_DIR [--provider none|ollama|claude]: build JOB_DIR/visual_index.json from the
job's normalized.mp4 (and reframe shots in plan.json, when there is one), then print its summary."""

import argparse
import sys
from pathlib import Path

from hypercut import plan as plan_mod
from hypercut.ingest import probe
from hypercut.plan import Source
from hypercut.vision import build_index, summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hypercut.vision", description=__doc__.splitlines()[0])
    ap.add_argument("job_dir")
    ap.add_argument("--provider", default=None, help="none (default), ollama (local) or claude (sends frames to Claude)")
    args = ap.parse_args(argv)
    job = Path(args.job_dir)
    mp4 = job / "normalized.mp4"
    plan_path = job / "plan.json"
    if plan_path.is_file():
        plan = plan_mod.load(plan_path)
        source, reframe = plan.source, plan.reframe
    else:
        meta = probe(mp4)
        source, reframe = Source(path=str(mp4), **meta), None
    print(summary(build_index(mp4, source, reframe, job, args.provider or "none")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
