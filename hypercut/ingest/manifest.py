"""What HyperCut knows about the uploaded file, written once at ingest as `manifest.json` (ADR 0104).

    describe(info, path) -> {"original": {...}, "video": {...}, "audio": {...}, "warnings": [...]}
    mark(job_dir, "transcribe", "done")   # per-stage status, so a job shows what was analysed

The manifest is about the media, like the visual index (ADR 0024), and stays out of `plan.json`. It records the
facts ingest had to deal with (variable frame rate, rotation, HDR, no sound, a low resolution) as plain warnings the
job page shows, and a SHA-256 of the original so a moved or renamed source can be recognised later.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from fractions import Fraction
from pathlib import Path

FILE = "manifest.json"
VERSION = 1
VFR_TOLERANCE = 0.01  # average vs nominal frame rate, relative
LOW_HEIGHT = 720  # the short side under this looks soft at 1080x1920
HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}  # PQ and HLG

_lock = threading.Lock()


def _rate(value: str | None) -> float:
    try:
        return float(Fraction(value or "0/1"))
    except (ZeroDivisionError, ValueError):
        return 0.0


def rotation(stream: dict) -> int:
    """Clockwise display rotation in degrees (0, 90, 180, 270) from the display matrix or the old `rotate` tag."""
    for side in stream.get("side_data_list") or []:
        if "rotation" in side:
            return int(round(-float(side["rotation"]))) % 360
    try:
        return int(stream.get("tags", {}).get("rotate", 0)) % 360
    except ValueError:
        return 0


def orientation(width: int, height: int) -> str:
    if abs(width - height) <= 0.02 * max(width, height):
        return "square"
    return "portrait" if height > width else "landscape"


def sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def describe(info: dict, path: Path) -> dict:
    """The manifest's media part from ffprobe's `-show_format -show_streams` JSON for `path`."""
    streams = info.get("streams", [])
    fmt = info.get("format", {})
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    turn = rotation(video)
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    shown = (height, width) if turn in (90, 270) else (width, height)
    nominal, average = _rate(video.get("r_frame_rate")), _rate(video.get("avg_frame_rate"))
    vfr = bool(nominal and average and abs(nominal - average) / nominal > VFR_TOLERANCE)
    hdr = video.get("color_transfer") in HDR_TRANSFERS
    first = audio[0] if audio else {}

    warnings = []
    if not audio:
        warnings.append("The video has no sound, so there are no captions and no cuts by speech. A silent track "
                        "was added; add music or text in the editor.")
    if vfr:
        warnings.append(f"The video has a variable frame rate (about {average:.1f} fps on average); it was "
                        "converted to a steady 30 fps so sound and picture stay in sync.")
    if turn:
        warnings.append(f"The video is stored rotated by {turn}°; it was turned upright.")
    if hdr:
        warnings.append("The video is HDR; it was converted to standard range, so colours may look a little flatter.")
    if min(shown) and min(shown) < LOW_HEIGHT:
        warnings.append(f"The video is {shown[0]}x{shown[1]}; at 1080x1920 it will look soft.")
    if len(audio) > 1:
        warnings.append(f"The video has {len(audio)} audio tracks; only the first is used.")

    return {
        "version": VERSION,
        "original": {
            "name": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "container": fmt.get("format_name"),
            "duration": round(float(video.get("duration") or fmt.get("duration") or 0), 3),
            "bitrate": int(fmt["bit_rate"]) if str(fmt.get("bit_rate", "")).isdigit() else None,
        },
        "video": {
            "codec": video.get("codec_name"),
            "width": width,
            "height": height,
            "rotation": turn,
            "display_width": shown[0],
            "display_height": shown[1],
            "orientation": orientation(*shown),
            "fps": round(average or nominal, 3),
            "variable_frame_rate": vfr,
            "pixel_format": video.get("pix_fmt"),
            "hdr": hdr,
        },
        "audio": {
            "present": bool(audio),
            "tracks": len(audio),
            "codec": first.get("codec_name"),
            "channels": first.get("channels"),
            "sample_rate": int(first["sample_rate"]) if str(first.get("sample_rate", "")).isdigit() else None,
        },
        "warnings": warnings,
        "stages": {},
    }


def load(job_dir: str | Path) -> dict | None:
    path = Path(job_dir) / FILE
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def save(job_dir: str | Path, manifest: dict) -> None:
    path = Path(job_dir) / FILE
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2))
    os.replace(tmp, path)


def update(job_dir: str | Path, **fields) -> None:
    """Merge top-level fields into the manifest (no-op without one)."""
    with _lock:
        manifest = load(job_dir)
        if manifest is not None:
            save(job_dir, {**manifest, **fields})


def mark(job_dir: str | Path, stage: str, status: str) -> None:
    """Record a stage as running, done, failed or skipped, with the time."""
    with _lock:
        manifest = load(job_dir)
        if manifest is None:
            return
        manifest.setdefault("stages", {})[stage] = {"status": status, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        save(job_dir, manifest)
