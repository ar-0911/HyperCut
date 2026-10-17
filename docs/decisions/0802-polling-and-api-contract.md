# 0802: Web: polling, and how the browser uses the job API

Status: accepted, 2026-10-17

**Decision.**
- Progress is plain polling of `GET /jobs/{id}`: every 1.5 s while `queued|running`, retrying every 4 s if the API is
  unreachable. The four stages (`ingest, transcribe, style, analyze`) are shown as steps from `job.stage`.
- A render is polled every 2 s until `render` leaves `running`. Editing the plan clears the local render state
  because the API does the same on `PUT /plan`.
- Errors from FastAPI (`detail` as string or validation list) are turned into one line; a network failure says the
  API cannot be reached.
- The style presets are listed in `web/lib/presets.ts` (mirror of `hypercut/style/presets.py`). A chip fills the
  prompt text; Claude maps the prompt to the nearest preset, so no new API field is needed.
- The browser calls the API directly, so the API needs CORS for the web origin (`http://localhost:3000`).
  `api/` is owned by another task and has no CORS middleware yet; a note was posted to that owner.

**Alternatives.** Server-sent events or websockets (the API has none, and jobs last minutes). A `/presets`
endpoint (small, but a cross-task API change for six static strings). A Next.js rewrite proxy (avoids CORS with no
API change, but hides the API URL setting; it is the fallback if CORS is not added).

**Consequences.** Polling is simple and survives restarts of either side. The presets list can drift from the
Python one; the cost is a stale chip label, not a failure.
