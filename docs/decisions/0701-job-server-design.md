# 0701: API: file-based jobs, background thread, shared pipeline function

Status: accepted, 2026-10-17

**Decision.**
- One FastAPI app (`api.main:app`). Endpoints: `POST /jobs` (multipart `video`, `style`, `hook_strategy`),
  `GET /jobs/{id}`, `PUT /jobs/{id}/plan`, `POST /jobs/{id}/render`, `GET /jobs/{id}/files/{name}`.
- Job state is `media/<job_id>/job.json` (status `queued|running|done|error`, current `stage`, `error`,
  `render` state). Written atomically (temp file + rename) under a lock. No database. `HYPERCUT_MEDIA`
  overrides the `media/` location. Job ids are 12 hex characters and validated, which also blocks path tricks.
- The pipeline lives in `hypercut.run.run_pipeline` (ingest, then transcribe and reframe at the same time,
  then style, then analyze, then `plan.json`). The API and the `python -m hypercut.run` CLI call the same
  function, so they cannot drift. Stage functions are looked up on the `hypercut.run` module so tests can
  monkeypatch them.
- The pipeline runs via FastAPI `BackgroundTasks` (a worker thread). Any exception becomes
  `status=error` with the message (stage errors such as `IngestError` are already user-safe). Jobs that were
  running when the server died stay `running`; restarting is manual for now.
- `PUT /plan` validates with the `EditPlan` model (invalid gives 422), only when the job is `done` and not
  rendering, and clears any earlier render state because it is stale.
- Render shells out to `npm run render -- --plan --video --out` in `render/`, one render at a time
  (semaphore). Output is `output.mp4`, fetched through the files endpoint, which only serves regular files
  directly inside the job folder and never `job.json`.

**Alternatives.** A task queue (Celery/RQ) or SQLite: more moving parts than a single-user local app needs
(ADR 0008). Calling Remotion from Python directly: the renderer is TypeScript, and the npm script is its
tested entry point. Running reframe after transcribe: it is independent and CPU-bound while Whisper is
too, but overlapping them still saves wall-clock time on a multi-core machine.

**Consequences.** One process, no auth, no cleanup of old jobs, and a job interrupted by a restart is not
resumed. All of these are fine locally and are the things to revisit if the app is ever hosted.
