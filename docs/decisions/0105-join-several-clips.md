# 0105. Several clips make one reel

Status: accepted (2026-10-26)

## What

`ingest_files(paths, job_dir)` joins two or more clips in the order given (`join`), then ingests the result as
one video. The joined video takes the first clip's picture size (capped at 1920 tall) and 30 fps; a clip of
another shape is fitted inside and the rest of the frame is a darkened, blurred copy of itself, never bars of
plain colour. A clip without sound gets silence. The total must fit the usual 10 s to 3 minutes. The manifest
lists each clip (name, size, SHA-256, duration, where it starts in the joined video) and their warnings,
prefixed with the clip's name.

`POST /jobs` takes the extra clips as `more` (at most 10 clips in all), the upload page has a "More clips" field,
and `python -m hypercut.run` takes several files. Retry finds them again (`upload-2.*`, `upload-3.*`, ...).

## Alternatives

- **A timeline of separate sources in the plan.** The right model for long multi-camera edits, but every stage
  and the renderer assume one source; joining keeps the contract (one `Source`).
- **Letterbox other shapes in black.** Against the rule that a reel never shows a plain background.

## Consequences

- A project of joined clips is always saved with its video (ADR 0027): there is no single original to find.
- The join is a hard cut; the face tracker sees it as one and the editorial cut style treats it like any other.
