# 0021. A job folder is a project: versions on disk, autosave and recovery

Status: accepted (2026-10-26)

## What

`hypercut/history.py` keeps every saved version of a job's plan in `media/<job>/history/` as a full snapshot
(`v0001.json`, ...) plus `index.json`: for each version its parent, who made it (`pipeline`, `edit`,
`assistant`, `review`, `restore`, `render`, `import`), an optional name, the request that made it, and what
changed in words (`hypercut.diff`, ADR 0022). `plan.json` stays the current plan, so every stage and the
renderer read exactly what they read before.

- The pipeline's first cut is version 1 (`run_pipeline` commits it). Older jobs get a history on first use:
  `plan.base.json` becomes version 1 and the current plan version 2.
- `PUT /jobs/{id}/plan` saves a version (`kind`, `note`, `label` as query parameters). Saving an identical
  plan adds nothing.
- Undo / redo (`POST /jobs/{id}/history/undo|redo`) move between versions and survive a reload or a crash.
  A new save after an undo starts a new branch; the undone versions stay listed.
- Going back to any version (`POST /history/{vid}/restore`) adds it as a new version, so nothing is lost.
  "Restore original" is the same thing for version 1.
- Versions can be named (`PATCH /history/{vid}`). Named and pipeline versions are never pruned; others are
  pruned oldest first past 300.
- Autosave: the editor writes unsaved edits to `draft.json` 2.5 s after each change (`PUT /draft`). On opening,
  a draft that differs from the current plan is offered back with what it changes ("Recover them" / "Discard").
  Saving a version clears it.
- Recovery: on server start, jobs left `queued`/`running` are marked `error` + `interrupted`, and renders,
  cut-outs and exports left `running` are marked failed with a plain message. `POST /jobs/{id}/retry` runs the
  pipeline again on the saved upload.
- Graphics drawn and pictures fetched just before a render are committed as a `render` version, so an undo
  never has to draw them again.

The editor keeps its in-memory undo for fine-grained timeline moves (instant, many steps per second); versions
are the durable layer on top, made on Save, on accepting an assistant edit, and on going back.

## Alternatives

- **An operation log (event sourcing) replayed from the first cut.** Smaller on disk, but every op type would
  need to replay identically forever, and drawing ops call Claude. Snapshots of 20-150 KB are cheap and a
  corrupt one only loses itself.
- **Git in the job folder.** Real history and diffs, but a dependency, opaque to the API, and its diffs are
  JSON lines, not "Removed 2.4 s at 0:12".
- **A database (SQLite).** Not needed yet: one writer per job and the job folder stays portable (ADR 0701).
- **Autosave straight into `plan.json`.** Would make every half-finished drag the "saved" edit and turn
  renders stale without the user asking; the draft keeps the two apart.

## Consequences

- Every change a user keeps is recoverable and explained, which the editing agent will rely on (it can
  propose, validate and roll back by version).
- The job folder grows by one snapshot per saved version (~10 MB worst case at the cap).
- `plan.base.json` is still written for older clients but nothing new reads it; version 1 is the original.
