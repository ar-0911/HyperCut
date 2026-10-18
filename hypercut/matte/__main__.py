"""python -m hypercut.matte VIDEO [--plan plan.json] [--out matte.webm]: write the speaker cut-out video."""

import argparse
import sys
import time
from pathlib import Path

from hypercut import plan as plan_mod
from hypercut.plan import Reframe
from hypercut.reframe.__main__ import _probe


def main(argv: list[str] | None = None) -> int:
    from hypercut.matte import MATTE_FILE, matte

    p = argparse.ArgumentParser(prog="python -m hypercut.matte", description=__doc__.splitlines()[0])
    p.add_argument("video", help="the normalized video of a job")
    p.add_argument("--plan", help="plan.json whose reframe keys pick the main speaker (default: largest person)")
    p.add_argument("--out", help=f"output file (default: {MATTE_FILE} next to the video)")
    args = p.parse_args(argv)
    source = _probe(args.video)
    reframe = plan_mod.load(args.plan).reframe if args.plan else Reframe()
    out = Path(args.out) if args.out else Path(args.video).with_name(MATTE_FILE)
    t0 = time.time()
    matte(args.video, source, reframe, out, on_progress=lambda k: print(f"matte {k:.0%}", file=sys.stderr))
    print(f"wrote {out} in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
