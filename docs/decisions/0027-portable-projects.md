# 0027. Portable projects: one `.hypercut` file per edit

Status: accepted (2026-10-26)

## What

`hypercut/project.py` packs a job folder into a `.hypercut` file, a zip of:

- `project.json`: format and version, whether the footage is inside, the original's size and SHA-256 (from the
  media manifest, ADR 0104), the normalized video's SHA-256, and the job state worth keeping (file name, style
  prompt, mode, the imports list); never ids, paths or run state.
- the edit: `plan.json`, `plan.base.json`, `history/` (every version and its names, ADR 0021), `draft.json`,
  `transcript.*`, `visual_index.json`, `manifest.json`;
- every file the plan shows: imports (`asset-*`), stock and generated media (`gen-*`), brand files (`brand-*`);
- with footage (the default): `normalized.mp4`, `audio.wav` and the speaker cut-out if one was made.

Sampled frames are left out (they are rebuilt when needed). Video and images are stored, not compressed again.

Opening (`unpack`, `POST /projects`, the upload page's "Or open a project") makes a new job, points every plan and
version at its own copy of the footage, and keeps the versions. A project saved without footage asks for the
original video: it must have the SHA-256 the project recorded, and is normalized again. `find_source` finds a
moved or renamed original under given folders by size first, then hash (`python -m hypercut.project unpack ...
--find ~/Videos`).

Saved from the editor's Finish panel ("Save the project": with the video, or without), `GET /jobs/{id}/project`,
or `python -m hypercut.project pack`.

## Alternatives

- **A folder instead of a zip.** Already what a job is; a single file is what people email, keep in a drive or
  move between machines.
- **Paths relative to the project.** Plans carry the footage's absolute path for the renderer; rewriting it on open
  keeps every other module unchanged.
- **Always including the original upload.** It can be large (4K camera files); the normalized video renders the
  same reel, and the original is only needed again for a project saved without footage.

## Why

Adi's product note asks for persistent, portable projects with moved-source detection. Everything a project needs
already lives in its job folder (ADR 0021, 0104, 0026 copy brand files in), so packing it is a file listing, not a
new data model.

## Consequences

- On the test footage: 51 MB with the video, 150 KB without; opening the light one with the original took 79 s,
  most of it normalizing the 4K source again, inside the request (fine locally; a background job if it is hosted).
- Projects from before the manifest have no hash, so a footage-less one accepts any video; the editor's checks
  (`missing_file`, word timings) still flag a mismatch.
- Zip entries are checked: only top-level files and `history/`, no absolute paths or `..`, at most 5000 entries.
