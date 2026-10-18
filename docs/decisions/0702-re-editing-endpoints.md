# 0702: API for re-editing: base plan, restore, imported files, assistant, job import

Status: accepted, 2026-10-18

**Decision.**
- *Keep the original.* The first `PUT /jobs/{id}/plan` copies the pipeline's `plan.json` to
  `plan.base.json`; `GET /jobs/{id}` returns it as `base_plan` (the current plan if nothing was edited).
  `POST /jobs/{id}/plan/restore` puts it back. The editor uses the base to list removed blocks so they can
  be dragged back. No numbered history on disk: undo/redo lives in the browser.
- *Imported files.* `POST /jobs/{id}/assets` (multipart `file`) accepts images (jpg, png, webp, gif, up to
  25 MB) and videos (mp4, mov, m4v, webm, mkv, avi, up to 500 MB), 30 per job. Clips are re-encoded with
  FFmpeg to silent 30 fps H.264, longest side at most 1920 and the first 60 s, so every browser previews them and the
  render reads them the same way. Files are stored flat as `asset-<12 hex><ext>` so the existing files
  endpoint serves them; their records (`name`, `kind`, `label`, `duration`) live in `job.json`. `DELETE
  /jobs/{id}/assets/{name}` refuses while the saved plan still uses the file. `PUT` rejects a plan whose
  `media` graphic names a file the job does not have.
- *Assistant.* `POST /jobs/{id}/assistant` with `{instruction, plan, playhead, selected}` runs ADR 0013 on
  the plan it is sent (the editor may have unsaved edits) and returns `{plan, message, changes}` without
  saving. A Claude failure (e.g. a usage limit) is a 502 with the reason.
- *CORS.* The browser calls the API directly (ADR 0802), so the API now allows the origins in
  `HYPERCUT_WEB_ORIGINS` (default `http://localhost:3000`). Before this the web app could not reach the API.
- *Job import.* `python -m api.import_job FOLDER [--plan NAME]` turns a CLI run's folder (plan +
  `normalized.mp4`) into a done web job, hard-linking files, so reels made outside the app can be re-edited.

**Alternatives.** Versioned plan files on every save (more to clean up; the browser's undo covers a
session and the base covers "start over"). Uploading B-roll as-is (HEVC .mov from a phone doesn't play in
Chrome or Firefox). Running the assistant against the saved plan only (would drop unsaved edits).

**Consequences.** Uploads block their request while FFmpeg converts (a few seconds for a minute of 1080p).
Imported files count against local disk under `media/`.
