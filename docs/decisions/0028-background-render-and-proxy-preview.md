# 0028. Keep editing during a render; a light preview copy

Status: accepted (2026-10-26)

## What

**Render from a snapshot.** `render_plan` copies `plan.json` to `render.plan.json` when it starts and does all of
its before-render work there (the cut-out, titles behind the speaker, drawings, fetched pictures), then renders the
snapshot. The editor can keep saving while it runs: `PUT /plan`, undo, the assistant and kits no longer answer 409
during a render, and a save no longer clears a running render's state. What the render drew or fetched goes back
into `plan.json` as a "render" version only when nobody edited meanwhile; otherwise the edits win and the next render
draws again. The job records `rendering_version` (the version at the start) and `render_version` (what the download
is), so the editor says "The download is version N; your edits since then need another render". QA checks the
output against the snapshot it was made from.

**Preview copy.** `make_proxy` writes `proxy.mp4` next to the normalized video: 960 px tall, a keyframe every half
second (`-g 15`) so scrubbing lands at once, CRF 26, the same frames and sound. The pipeline makes it alongside face
tracking; for older or opened jobs the API makes it the first time the job is asked for. The editor plays it when it
is there and the full video otherwise. Renders always use the full video. A video already 960 px tall or less gets
no copy.

## Alternatives

- **Queue edits until the render ends.** Simple, but a 5–50 minute render (3D moments render in software) locks
  the editor for that long, which is the complaint this fixes.
- **Render in a copied job folder.** Isolates everything, but copies the footage per render and makes merging back
  the drawn graphics harder than one snapshot file.
- **Incremental render (re-render only changed spans).** The bigger win for repeat exports, but needs Remotion
  chunk caching keyed by plan spans; left for later. The snapshot is a precondition for it.
- **Proxy at 720 px or lower.** Lighter still, but captions and small card text in the preview get hard to judge.

## Consequences

- One render at a time per server (unchanged); edits during it are safe.
- A render's drawings can be lost if the plan was edited meanwhile; they are redrawn on the next render (a Claude
  call on the subscription, not a cost in money).
- `proxy.mp4` adds about a tenth of the normalized video's size to the job folder; it is not put in projects
  (ADR 0027) since it is rebuilt on open.
