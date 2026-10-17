"""hypercut.ingest: probe, validate length, normalize to CFR H.264/AAC, extract 16 kHz mono wav."""

from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path

from hypercut.plan import Source

MIN_SECONDS = 10.0
MAX_SECONDS = 180.0
TARGET_FPS = 30
MAX_HEIGHT = 1920  # the 1080x1920 output never needs more source pixels than this (ADR 0103)


class IngestError(ValueError):
    """The input can't be used; the message is safe to show to the user."""


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise IngestError(f"{cmd[0]} is not installed; install FFmpeg to use HyperCut") from None


def probe(path: Path) -> dict:
    """Return width, height, fps, duration and has_audio for the first video stream."""
    res = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    if res.returncode != 0:
        raise IngestError(f"Could not read {Path(path).name} as a video: {res.stderr.strip() or 'ffprobe failed'}")
    info = json.loads(res.stdout)
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise IngestError(f"{Path(path).name} has no video stream")
    if not any(s.get("codec_type") == "audio" for s in streams):
        raise IngestError(f"{Path(path).name} has no audio track; HyperCut needs speech to transcribe")
    duration = float(video.get("duration") or info.get("format", {}).get("duration") or 0)
    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
    try:
        fps = float(Fraction(rate))
    except (ZeroDivisionError, ValueError):
        fps = 0.0
    return {
        "width": int(video["width"]),
        "height": int(video["height"]),
        "fps": fps,
        "duration": duration,
    }


def validate_duration(duration: float) -> None:
    if duration < MIN_SECONDS:
        raise IngestError(f"Video is {duration:.1f}s long; the minimum is {MIN_SECONDS:.0f}s")
    if duration > MAX_SECONDS:
        raise IngestError(
            f"Video is {duration:.0f}s long; the maximum is {MAX_SECONDS:.0f}s (3 minutes). Trim it and try again"
        )


def ingest(input_path: str | Path, job_dir: str | Path) -> tuple[Source, Path, Path]:
    """Probe and validate `input_path`, then write normalized.mp4 and audio.wav into `job_dir`."""
    input_path, job_dir = Path(input_path), Path(job_dir)
    if not input_path.is_file():
        raise IngestError(f"Input file not found: {input_path}")
    meta = probe(input_path)
    validate_duration(meta["duration"])

    job_dir.mkdir(parents=True, exist_ok=True)
    mp4, wav = job_dir / "normalized.mp4", job_dir / "audio.wav"

    # Rotation metadata is applied by ffmpeg's autorotate, so the probed size may be pre-rotation;
    # the final size is re-probed from the normalized file below.
    res = _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(input_path),
        "-map", "0:v:0", "-map", "0:a:0",
        "-vf", f"fps={TARGET_FPS},scale=-2:'min(ih,{MAX_HEIGHT})'", "-fps_mode", "cfr",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", str(mp4),
    ])
    if res.returncode != 0:
        raise IngestError(f"Could not normalize the video: {res.stderr.strip()}")
    res = _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(mp4),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav),
    ])
    if res.returncode != 0:
        raise IngestError(f"Could not extract audio: {res.stderr.strip()}")

    out = probe(mp4)
    source = Source(
        path=str(mp4), width=out["width"], height=out["height"], fps=round(out["fps"], 3), duration=out["duration"]
    )
    return source, mp4, wav
