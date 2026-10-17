# 0102: Ingest validates with ffprobe and raises IngestError

Status: accepted, 2026-10-17

**Decision.** Before encoding, ingest probes with `ffprobe` and rejects: unreadable files, files with no video
stream, files with no audio track, and durations under 10 s or over 180 s (limits from ADR 0002). All raise
`IngestError` (a `ValueError`) with a user-presentable message; the CLI prints it and exits 1. FFmpeg is called
through `subprocess` with no extra Python dependency.

**Alternatives.** A Python binding such as PyAV or ffmpeg-python (extra dependency, heavier install). Accepting
silent video (nothing to transcribe, so the whole pipeline would produce an empty edit). Validating after
normalizing (wastes an encode on inputs that will be rejected).

**Why.** Failing early with a clear message is cheaper than failing in transcribe. A single exception type lets
the API stage map it to a 4xx response.

**Consequences.** Duration comes from the video stream, falling back to the container. Limits are the module
constants `MIN_SECONDS` / `MAX_SECONDS`.
