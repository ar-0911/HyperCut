"""python -m hypercut.reframe VIDEO: print the reframe keys as JSON."""

import argparse
import json
import subprocess

from hypercut.plan import Source


def _probe(path: str) -> Source:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate:format=duration", "-of", "json", path],
        check=True, capture_output=True, text=True,
    ).stdout
    info = json.loads(out)
    s = info["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return Source(path=path, width=s["width"], height=s["height"], fps=float(num) / float(den),
                  duration=float(info["format"]["duration"]))


def main() -> None:
    from hypercut.reframe import reframe

    p = argparse.ArgumentParser(prog="python -m hypercut.reframe")
    p.add_argument("video")
    args = p.parse_args()
    print(reframe(args.video, _probe(args.video)).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
