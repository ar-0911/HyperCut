"""Post-export validation: inspect the rendered mp4 itself, not the fact that the render exited cleanly (ADR 0023).

    validate(plan, "media/<job>/output.mp4") -> {"ok": bool, "checks": [{"name", "status", "detail"}, ...]}

With ffprobe and FFmpeg's own filters (no models, a few seconds per minute of video):
- the file opens and has one video and one audio stream
- size and frame rate are what the plan asks for
- duration matches the plan's reel length, and audio and video end together
- no black frames other than the fade in / fade out
- no frozen picture (a stuck frame for over a second)
- no dropouts of silence inside the reel
- loudness close to the -14 LUFS platforms normalize to, true peak under -1 dBTP

"fail" means the file is broken or not what was asked for; "warn" means worth a look. `python -m hypercut.qa
JOB_DIR` checks `output.mp4` against `plan.json` and writes `output.qa.json`.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from hypercut import plan as plan_mod
from hypercut.plan import EditPlan

TARGET_LUFS = -14.0
LUFS_TOLERANCE = 3.0
MAX_TRUE_PEAK = -1.0
FREEZE_SECONDS = 1.0
SILENCE_SECONDS = 1.2
BLACK_SECONDS = 0.25
QA_FILE = "output.qa.json"


class QAError(RuntimeError):
    pass


def _ffmpeg_log(video: Path, *filters: str, audio: bool = False, timeout: int = 600) -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise QAError("FFmpeg is not installed")
    flag = "-af" if audio else "-vf"
    cmd = [exe, "-hide_banner", "-nostats", "-i", str(video), flag, ",".join(filters), "-f", "null", "-"]
    if not audio:
        cmd[cmd.index("-f"):cmd.index("-f")] = ["-an"]
    else:
        cmd[cmd.index("-f"):cmd.index("-f")] = ["-vn"]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stderr


def probe(video: Path) -> dict:
    exe = shutil.which("ffprobe")
    if not exe:
        raise QAError("ffprobe is not installed")
    res = subprocess.run([exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(video)],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise QAError(f"the file does not open as a video: {res.stderr.strip()[:300]}")
    return json.loads(res.stdout)


def _ranges(log: str, start_key: str, end_key: str) -> list[tuple[float, float]]:
    starts = [float(x) for x in re.findall(rf"{start_key}[:=]\s*(-?[\d.]+)", log)]
    ends = [float(x) for x in re.findall(rf"{end_key}[:=]\s*(-?[\d.]+)", log)]
    return [(max(s, 0.0), e) for s, e in zip(starts, ends) if e > s]


def _check(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": detail}


def validate(plan: EditPlan, video: str | Path) -> dict:
    video = Path(video)
    checks: list[dict] = []
    if not video.is_file():
        return {"ok": False, "checks": [_check("file", "fail", "the rendered file is missing")]}
    try:
        info = probe(video)
    except QAError as e:
        return {"ok": False, "checks": [_check("file", "fail", str(e))]}

    streams = info.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if v is None:
        return {"ok": False, "checks": [_check("streams", "fail", "no video stream")]}
    checks.append(_check("audio", "pass" if a else "fail", "audio track present" if a else "no audio track"))

    want = plan.output
    size_ok = (int(v["width"]), int(v["height"])) == (want.width, want.height)
    checks.append(_check("size", "pass" if size_ok else "fail", f"{v['width']}x{v['height']} (asked for {want.width}x{want.height})"))
    num, _, den = str(v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    checks.append(_check("frame_rate", "pass" if abs(fps - want.fps) < 0.05 else "fail", f"{fps:.2f} fps (asked for {want.fps:g})"))

    duration = float(info.get("format", {}).get("duration") or v.get("duration") or 0)
    expected = plan.output_duration()
    # Each piece is rounded to whole frames by the renderer.
    tolerance = 0.2 + len(plan.segments) / want.fps
    status = "pass" if abs(duration - expected) <= tolerance else "fail"
    checks.append(_check("duration", status, f"{duration:.2f} s (the plan is {expected:.2f} s)"))
    if a is not None:
        vd, ad = float(v.get("duration") or duration), float(a.get("duration") or duration)
        checks.append(_check("av_sync", "pass" if abs(vd - ad) <= 0.1 else "fail",
                             f"video {vd:.2f} s, audio {ad:.2f} s" + ("" if abs(vd - ad) <= 0.1 else ": they end apart")))

    try:
        tr = plan.style.transitions
        lo, hi = tr.fade_in + 0.1, duration - tr.fade_out - 0.1
        black = [r for r in _ranges(_ffmpeg_log(video, f"blackdetect=d={BLACK_SECONDS}:pix_th=0.08"), "black_start", "black_end")
                 if r[1] > lo and r[0] < hi]
        checks.append(_check("black_frames", "fail" if black else "pass",
                             "; ".join(f"black {s:.1f}-{e:.1f} s" for s, e in black[:5]) or "none outside the fades"))

        frozen = [r for r in _ranges(_ffmpeg_log(video, f"freezedetect=n=0.001:d={FREEZE_SECONDS}"),
                                     "lavfi.freezedetect.freeze_start", "lavfi.freezedetect.freeze_end")
                  if r[1] > lo and r[0] < hi]
        checks.append(_check("frozen_frames", "warn" if frozen else "pass",
                             "; ".join(f"still {s:.1f}-{e:.1f} s" for s, e in frozen[:5]) or "none"))

        if a is not None:
            silent = [r for r in _ranges(_ffmpeg_log(video, f"silencedetect=noise=-50dB:d={SILENCE_SECONDS}", audio=True),
                                         "silence_start", "silence_end") if r[1] > lo and r[0] < hi]
            checks.append(_check("audio_dropouts", "warn" if silent else "pass",
                                 "; ".join(f"silent {s:.1f}-{e:.1f} s" for s, e in silent[:5]) or "none"))
            log = _ffmpeg_log(video, "ebur128=peak=true", audio=True)
            lufs = re.findall(r"I:\s*(-?[\d.]+) LUFS", log)
            peak = re.findall(r"Peak:\s*(-?[\d.]+|-inf) dBFS", log)
            if lufs:
                i = float(lufs[-1])
                ok = abs(i - TARGET_LUFS) <= LUFS_TOLERANCE
                checks.append(_check("loudness", "pass" if ok else "warn", f"{i:.1f} LUFS (target {TARGET_LUFS:g})"))
            if peak and peak[-1] != "-inf":
                p = float(peak[-1])
                checks.append(_check("true_peak", "pass" if p <= MAX_TRUE_PEAK else "warn", f"{p:.1f} dBTP (keep under {MAX_TRUE_PEAK:g})"))
    except (QAError, subprocess.TimeoutExpired) as e:
        checks.append(_check("analysis", "warn", f"could not analyse the picture and sound: {e}"))

    return {"ok": not any(c["status"] == "fail" for c in checks), "checks": checks}


def validate_job(job_dir: str | Path, video_name: str = "output.mp4") -> dict:
    """Validate a job's render against its plan and save the result next to it."""
    job_dir = Path(job_dir)
    result = validate(plan_mod.load(job_dir / "plan.json"), job_dir / video_name)
    (job_dir / QA_FILE).write_text(json.dumps(result, indent=2) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hypercut.qa", description="Validate a rendered reel against its plan.")
    ap.add_argument("job_dir")
    ap.add_argument("--video", default="output.mp4")
    args = ap.parse_args(argv)
    result = validate_job(args.job_dir, args.video)
    for c in result["checks"]:
        print(f"{c['status']:>4}  {c['name']:<15} {c['detail']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
