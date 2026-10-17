"""python -m hypercut.ingest <file> <out_dir>"""

from __future__ import annotations

import argparse
import sys

from hypercut.ingest import IngestError, ingest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hypercut.ingest", description="Normalize a video and extract audio.")
    ap.add_argument("input")
    ap.add_argument("out_dir")
    args = ap.parse_args(argv)
    try:
        source, mp4, wav = ingest(args.input, args.out_dir)
    except IngestError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(source.model_dump_json(indent=2))
    print(f"video: {mp4}\naudio: {wav}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
