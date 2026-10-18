"""Footage and pictures the user imports in the editor. See docs/decisions/0702-*.

Each upload is stored flat in the job folder as `asset-<12 hex><ext>` so the existing files endpoint serves
it and the renderer can link it next to the video. Clips are re-encoded to a short silent H.264 mp4 so every
browser previews them and Remotion renders them the same way.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
MAX_ASSETS = 30
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_VIDEO_BYTES = 500 * 1024 * 1024
MAX_CLIP_SECONDS = 60.0  # longer clips are cut to their first minute
MAX_CLIP_SIDE = 1920  # longest side; the output is 1080x1920
ASSET_NAME = re.compile(r"^asset-[0-9a-f]{12}\.(jpg|jpeg|png|webp|gif|mp4)$")


class AssetError(ValueError):
    pass


def kind_of(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    raise AssetError(f"{filename or 'file'}: use an image ({', '.join(sorted(IMAGE_EXT))}) "
                     f"or a video ({', '.join(sorted(VIDEO_EXT))})")


def is_asset_name(name: str) -> bool:
    return bool(ASSET_NAME.match(name))


def probe_duration(path: Path) -> float:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(json.loads(res.stdout)["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        raise AssetError("could not read that file as a video") from None


def prepare_video(src: Path, out: Path) -> float:
    """Re-encode `src` to a silent H.264 mp4 at `out` (first minute, longest side at most 1920). Returns its length."""
    res = subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-i", str(src), "-t", str(MAX_CLIP_SECONDS), "-an",
            "-vf", f"scale='min({MAX_CLIP_SIDE},iw)':'min({MAX_CLIP_SIDE},ih)':force_original_aspect_ratio=decrease"
                   ":flags=bicubic,scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=30,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-movflags", "+faststart", str(out),
        ],
        capture_output=True, text=True,
    )
    if res.returncode != 0 or not out.is_file():
        out.unlink(missing_ok=True)
        raise AssetError("could not convert that video: " + (res.stderr.strip()[-300:] or "ffmpeg failed"))
    return probe_duration(out)


def add(job_dir: Path, upload: Path, filename: str, existing: int) -> dict:
    """Turn a saved upload into a job asset. Returns its record for job.json; removes `upload`."""
    try:
        if existing >= MAX_ASSETS:
            raise AssetError(f"a job can hold up to {MAX_ASSETS} imported files")
        kind = kind_of(filename)
        size = upload.stat().st_size
        limit = MAX_IMAGE_BYTES if kind == "image" else MAX_VIDEO_BYTES
        if size > limit:
            raise AssetError(f"{filename} is {size // 2**20} MB; the limit for a {kind} is {limit // 2**20} MB")
        stem = "asset-" + uuid.uuid4().hex[:12]
        record = {"kind": kind, "label": Path(filename).stem[:80] or kind}
        if kind == "image":
            ext = Path(filename).suffix.lower()
            name = stem + ext
            shutil.move(str(upload), job_dir / name)
        else:
            name = stem + ".mp4"
            record["duration"] = round(prepare_video(upload, job_dir / name), 3)
        record["name"] = name
        return record
    finally:
        upload.unlink(missing_ok=True)
