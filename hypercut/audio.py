"""Loudness of the finished reel (ADR 0616): every export lands at the level platforms play shorts at.

    normalize("output.mp4")   # in place: -14 LUFS integrated, true peak under -1.5 dBTP; the picture is copied

Two-pass FFmpeg `loudnorm`: the first pass measures, the second applies one linear gain (no pumping) with a true-peak
limiter only where needed. Speech recorded quietly or hot comes out the same, and nothing clips (the export check,
ADR 0023, flags what is left). `HYPERCUT_LOUDNESS` sets the target in LUFS, or "off".
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

TARGET = -14.0
TRUE_PEAK = -1.5
RANGE = 11.0


def target() -> float | None:
    value = os.environ.get("HYPERCUT_LOUDNESS", "").strip().lower()
    if value == "off":
        return None
    try:
        return float(value) if value else TARGET
    except ValueError:
        return TARGET


def measure(mp4: Path, lufs: float = TARGET) -> dict | None:
    exe = shutil.which("ffmpeg")
    if not exe:
        return None
    res = subprocess.run([exe, "-hide_banner", "-nostats", "-i", str(mp4), "-vn", "-af",
                          f"loudnorm=I={lufs}:TP={TRUE_PEAK}:LRA={RANGE}:print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True, timeout=600)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", res.stderr, re.S)
    return json.loads(m.group(0)) if m else None


def normalize(mp4: str | Path, lufs: float | None = None) -> dict | None:
    """Normalize the reel's sound in place; returns the first pass's measurement, or None if nothing was done."""
    mp4 = Path(mp4)
    lufs = target() if lufs is None else lufs
    if lufs is None:
        return None
    m = measure(mp4, lufs)
    if not m or m.get("input_i") in ("-inf", None):  # silent or no audio track
        return None
    tmp = mp4.with_name(mp4.stem + ".loudnorm" + mp4.suffix)
    res = subprocess.run([
        shutil.which("ffmpeg") or "ffmpeg", "-y", "-v", "error", "-i", str(mp4), "-c:v", "copy", "-af",
        f"loudnorm=I={lufs}:TP={TRUE_PEAK}:LRA={RANGE}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
        f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true",
        "-ar", "48000", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(tmp),
    ], capture_output=True, text=True, timeout=600)
    if res.returncode != 0 or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"loudness normalization failed: {res.stderr.strip()[-300:]}")
    tmp.replace(mp4)
    return m
