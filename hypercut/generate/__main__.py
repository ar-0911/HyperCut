"""python -m hypercut.generate JOB_DIR [--plan plan.json] [--regenerate ID [--prompt TEXT]]

Fetches every picture and clip the plan in JOB_DIR still waits for (stock footage, generated stills and clips),
saves them in the folder and writes the plan back. Needs FAL_KEY or HYPERCUT_GEN_LOCAL=1 for generation and
PEXELS_API_KEY, PIXABAY_API_KEY or HYPERCUT_STOCK=commons for stock.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hypercut import plan as plan_mod
from hypercut.generate import available, generate, pending, regenerate, spent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hypercut.generate", description=__doc__.splitlines()[0])
    ap.add_argument("job_dir")
    ap.add_argument("--plan", default="plan.json")
    ap.add_argument("--regenerate", metavar="ID", help="fetch this graphic again with a new seed")
    ap.add_argument("--prompt", help="with --regenerate: a new prompt (or search words for stock)")
    args = ap.parse_args(argv)
    path = Path(args.job_dir) / args.plan
    plan = plan_mod.load(path)
    if args.regenerate:
        plan = regenerate(plan, args.regenerate, args.prompt)
    todo = pending(plan)
    print(f"{len(todo)} to fetch; this machine can fetch: {', '.join(sorted(available())) or 'nothing (no keys set)'}")
    plan = generate(plan, args.job_dir)
    plan_mod.save(plan, path)
    for g in plan.graphics:
        req = g.props.get("generate")
        if isinstance(req, dict):
            print(f"  {g.id}: {req.get('file') or 'failed: ' + str(req.get('failed'))}")
    ledger = spent(args.job_dir)
    print(f"spent ${ledger['spent']:.2f} of ${ledger['budget']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
