# 0030. Opt-in usage counts kept on this computer; sharing without an upload

Status: accepted (2026-10-26)

## What

**Usage counts** (`hypercut/telemetry.py`). Off by default; the upload page's "More options" has the switch.
When on, the API appends small events to `media/telemetry.jsonl`: a job created (mode, and whether a kit, pictures,
a recipe or a style prompt were used, as yes/no), a job done (how long it took, how long the reel is), a stage
that failed, render and QA results, saved edits by kind, projects saved and opened, kits applied, and from the web
app the first-steps suggestion (shown, tried, kept, put back, skipped), the view switch, downloads and shares.
Every event has a fixed list of fields that are numbers, yes/no, or one of a fixed set of words; anything else,
and any unknown event, is dropped before writing. `GET /telemetry` gives a summary (counts, render success,
how often the suggestion is kept, median times) and the field list; `GET /telemetry/file` downloads the log;
`DELETE /telemetry` empties it. The log is trimmed past 2 MB.

**Share.** After a render, "Share" opens the system share sheet with the mp4 and a caption (the hook line and
`#shorts`) where the browser can share files; otherwise it downloads the mp4 and copies the caption.

## Alternatives

- **Send counts to a server.** Needed for a hosted product, but HyperCut is local-first (ADR 0015) and has no
  server of its own; a person who wants to help can send the file. The event list is the contract a future
  upload would use, and it would need its own opt-in.
- **Free-text events or error messages.** Richer, but an error message can carry a file name or a line of the
  transcript. Stages and counts only.
- **Share links to a hosted copy.** Needs hosting and storage of people's videos; out of scope for local-first.

## Consequences

- Pricing and a free tier are not decided here: they belong to a hosted version. These counts are what that
  decision would be made from (which features are used, how long renders take, what fails).
- Adding an event or field means adding it to `EVENTS`, which is the reviewable list of what is ever recorded.
