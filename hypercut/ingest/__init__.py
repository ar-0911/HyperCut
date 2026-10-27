"""hypercut.ingest: probe, validate length, normalize to CFR H.264/AAC, extract 16 kHz mono wav, write manifest.json."""

from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path

from hypercut.ingest import manifest
from hypercut.plan import Source

MIN_SECONDS = 10.0
MAX_SECONDS = 180.0
TARGET_FPS = 30
MAX_HEIGHT = 1920  # the 1080x1920 output never needs more source pixels than this (ADR 0103)
PROXY_FILE = "proxy.mp4"
PROXY_HEIGHT = 960  # the editor's preview plays this, not the full-size video (ADR 0028)


class IngestError(ValueError):
    """The input can't be used; the message is safe to show to the user."""


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise IngestError(f"{cmd[0]} is not installed; install FFmpeg to use HyperCut") from None


def _probe_json(path: Path) -> dict:
    res = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    if res.returncode != 0:
        raise IngestError(f"Could not read {Path(path).name} as a video: {res.stderr.strip() or 'ffprobe failed'}")
    info = json.loads(res.stdout)
    if not any(s.get("codec_type") == "video" for s in info.get("streams", [])):
        raise IngestError(f"{Path(path).name} has no video stream")
    return info


def probe(path: Path, info: dict | None = None) -> dict:
    """Return width, height, fps, duration and has_audio for the first video stream."""
    info = info or _probe_json(path)
    streams = info.get("streams", [])
    video = next(s for s in streams if s.get("codec_type") == "video")
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
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


LONG_SECONDS = 3600.0  # a long recording the editing agent makes several reels from (ADR 0031)


def validate_duration(duration: float, max_seconds: float = MAX_SECONDS) -> None:
    if duration < MIN_SECONDS:
        raise IngestError(f"Video is {duration:.1f}s long; the minimum is {MIN_SECONDS:.0f}s")
    if duration > max_seconds:
        if max_seconds == MAX_SECONDS:
            raise IngestError(
                f"Video is {duration:.0f}s long; the maximum for one reel is {MAX_SECONDS:.0f}s (3 minutes). Trim it, "
                "or make several reels from it"
            )
        raise IngestError(f"Video is {duration / 60:.0f} minutes long; the maximum is {max_seconds / 60:.0f} minutes")


def ingest(input_path: str | Path, job_dir: str | Path, max_seconds: float = MAX_SECONDS) -> tuple[Source, Path, Path]:
    """Probe and validate `input_path`, then write normalized.mp4, audio.wav and manifest.json into `job_dir`.

    A video without sound gets a silent track (ADR 0104): it still becomes a reel, without captions or speech cuts.
    """
    input_path, job_dir = Path(input_path), Path(job_dir)
    if not input_path.is_file():
        raise IngestError(f"Input file not found: {input_path}")
    info = _probe_json(input_path)
    meta = probe(input_path, info)
    validate_duration(meta["duration"], max_seconds)

    job_dir.mkdir(parents=True, exist_ok=True)
    mp4, wav = job_dir / "normalized.mp4", job_dir / "audio.wav"

    # Rotation metadata is applied by ffmpeg's autorotate, so the probed size may be pre-rotation;
    # the final size is re-probed from the normalized file below.
    silence = [] if meta["has_audio"] else ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    res = _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(input_path), *silence,
        "-map", "0:v:0", "-map", "0:a:0" if meta["has_audio"] else "1:a:0", *([] if meta["has_audio"] else ["-shortest"]),
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
    facts = manifest.describe(info, input_path)
    facts["normalized"] = {"path": mp4.name, "width": source.width, "height": source.height, "fps": source.fps,
                           "duration": round(source.duration, 3)}
    facts["stages"] = {"ingest": {"status": "done"}}
    manifest.save(job_dir, facts)
    return source, mp4, wav


def make_proxy(mp4: str | Path, out: str | Path | None = None) -> Path | None:
    """A small copy of the normalized video for the editor's preview (ADR 0028): 960 px tall, a keyframe every half
    second so scrubbing lands at once, the same frames and sound. None when the video is already that small."""
    mp4 = Path(mp4)
    out = Path(out) if out else mp4.with_name(PROXY_FILE)
    if probe(mp4)["height"] <= PROXY_HEIGHT:
        return None
    tmp = out.with_name(out.stem + ".part.mp4")
    res = _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(mp4),
        "-vf", f"scale=-2:{PROXY_HEIGHT}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-g", "15",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(tmp),
    ])
    if res.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise IngestError(f"Could not make the preview copy: {res.stderr.strip()}")
    tmp.replace(out)
    return out


JOINED_FILE = "joined.mp4"


def join(paths: list[str | Path], out: str | Path) -> Path:
    """Several clips of one recording session played back to back as one video (ADR 0105), at the first clip's
    picture size and 30 fps. A clip of another shape is fitted inside and the rest of the frame is filled with
    a blurred copy of itself (never bars of plain colour); a clip without sound gets silence."""
    paths, out = [Path(p) for p in paths], Path(out)
    if len(paths) < 2:
        raise IngestError("joining needs at least two clips")
    metas = []
    for p in paths:
        if not p.is_file():
            raise IngestError(f"Input file not found: {p}")
        info = _probe_json(p)
        meta = probe(p, info)
        turn = manifest.rotation(next(s for s in info["streams"] if s.get("codec_type") == "video"))
        if turn in (90, 270):
            meta["width"], meta["height"] = meta["height"], meta["width"]
        metas.append(meta)
    validate_duration(sum(m["duration"] for m in metas))
    first = metas[0]
    height = min(first["height"], MAX_HEIGHT) // 2 * 2
    width = round(first["width"] * height / first["height"]) // 2 * 2

    inputs: list[str] = []
    for p, m in zip(paths, metas):
        inputs += ["-i", str(p)]
    graph, joined = [], []
    n = len(paths)
    for i, m in enumerate(metas):
        if not m["has_audio"]:
            inputs += ["-f", "lavfi", "-t", f"{m['duration']:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        audio = f"{i}:a:0" if m["has_audio"] else f"{n + sum(1 for x in metas[:i] if not x['has_audio'])}:a:0"
        graph.append(
            f"[{i}:v:0]fps={TARGET_FPS},setsar=1,split[f{i}][b{i}];"
            f"[b{i}]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=40:3,eq=brightness=-0.12[bb{i}];"
            f"[f{i}]scale={width}:{height}:force_original_aspect_ratio=decrease[ff{i}];"
            f"[bb{i}][ff{i}]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[v{i}];"
            f"[{audio}]aresample=48000,aformat=channel_layouts=stereo[a{i}]"
        )
        joined.append(f"[v{i}][a{i}]")
    graph.append(f"{''.join(joined)}concat=n={n}:v=1:a=1[v][a]")
    res = _run([
        "ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(out),
    ])
    if res.returncode != 0:
        raise IngestError(f"Could not join the clips: {res.stderr.strip()[-500:]}")
    return out


def ingest_files(paths: list[str | Path], job_dir: str | Path) -> tuple[Source, Path, Path]:
    """`ingest` for one clip or several (joined first, in order). The manifest lists each clip (ADR 0105)."""
    paths, job_dir = [Path(p) for p in paths], Path(job_dir)
    if len(paths) == 1:
        return ingest(paths[0], job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    joined = join(paths, job_dir / JOINED_FILE)
    source, mp4, wav = ingest(joined, job_dir)
    parts, warnings, start = [], [], 0.0
    for p in paths:
        facts = manifest.describe(_probe_json(p), p)
        parts.append({**facts["original"], "start": round(start, 3)})
        start += facts["original"]["duration"]
        warnings += [f"{p.name}: {w}" for w in facts["warnings"]]
    joined.unlink(missing_ok=True)
    facts = manifest.load(job_dir) or {}
    facts["parts"] = parts
    facts["warnings"] = [f"{len(paths)} clips were joined in the order given."] + warnings
    manifest.save(job_dir, facts)
    return source, mp4, wav
