# 0008: Local web app with files on disk

Status: accepted, 2026-10-17

**Decision.** A FastAPI server (`api/`) runs the pipeline as one job per upload, in a background worker, and
keeps all files under `media/<job_id>/`. A Next.js app (`web/`) is the interface. No login, no cloud storage.

**Alternatives.** A CLI only; a desktop app; S3 storage and a hosted queue.

**Why.** A web UI is needed anyway to pick hooks, edit the transcript and preview. Running locally keeps it
free and simple while it is a personal tool.

**Consequences.** Moving to hosted use later means adding auth, object storage, a real job queue and the API
Claude backend (ADR 0003). The stage functions don't change.
