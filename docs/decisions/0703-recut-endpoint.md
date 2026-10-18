# 0703: Re-cut endpoint for new pacing

Status: accepted, 2026-10-18

**Decision.** `POST /jobs/{id}/recut` takes a plan, rebuilds its segments from `style.pacing` with the job's
`audio.wav` (`hypercut.analyze.cuts.recut`) and returns the plan without saving it. The assistant endpoint
passes the same wav so a `pacing.keep_pause` change re-cuts too.

**Alternatives.** Re-cut in the browser from word timings only (misses the silences FFmpeg finds).

**Why.** The editor is unsaved-by-default (undo, then Save), so the server only computes.

**Consequences.** Re-cutting brings back segments the user deleted by hand; the editor says so next to the
control, and undo restores them.
