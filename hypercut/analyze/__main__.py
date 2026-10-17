"""python -m hypercut.analyze plan.json [--wav audio.wav] [--strategy trim] [--visuals] [-o out.json]

Reads a plan holding source, transcript and style; writes it back with the
analyze fields filled in. Calls Claude.
"""

import argparse

from hypercut import plan as plan_mod
from hypercut.analyze import analyze

ap = argparse.ArgumentParser(prog="python -m hypercut.analyze")
ap.add_argument("plan")
ap.add_argument("--wav")
ap.add_argument("--strategy", choices=["cold_open", "trim"], default="cold_open")
ap.add_argument("--visuals", action="store_true", help="mix layouts and draw illustrations per beat")
ap.add_argument("-o", "--out")
args = ap.parse_args()

base = plan_mod.load(args.plan)
result = analyze(base.transcript, base.source, base.style, audio_wav=args.wav, strategy=args.strategy, visuals=args.visuals)
plan_mod.save(result, args.out or args.plan)
print(
    f"{len(result.hook.candidates)} hooks, {len(result.segments)} segments, "
    f"{len(result.graphics)} graphics, {len(result.zooms)} zooms, {len(result.layout)} layout spans"
)
