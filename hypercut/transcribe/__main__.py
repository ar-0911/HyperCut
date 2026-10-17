"""python -m hypercut.transcribe AUDIO.wav [--backend whisper|deepgram] [--out transcript.json] [--srt out.srt]"""

from __future__ import annotations

import argparse
import sys

from hypercut.transcribe import TranscribeError, to_srt, transcribe


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m hypercut.transcribe", description="Transcribe a wav file.")
    p.add_argument("wav")
    p.add_argument("--backend", choices=["whisper", "deepgram"], help="default: HYPERCUT_TRANSCRIBE or whisper")
    p.add_argument("--out", help="write the transcript JSON here (default: stdout)")
    p.add_argument("--srt", help="also write an SRT file here")
    args = p.parse_args(argv)
    try:
        t = transcribe(args.wav, args.backend)
    except TranscribeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    js = t.model_dump_json(indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(js + "\n")
    else:
        print(js)
    if args.srt:
        with open(args.srt, "w") as f:
            f.write(to_srt(t))
    return 0


if __name__ == "__main__":
    sys.exit(main())
