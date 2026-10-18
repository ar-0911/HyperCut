# 0013: The editor's assistant returns edit operations, not a new plan

Status: accepted, 2026-10-18

**Decision.**
- `hypercut/assistant.py` turns a plain-language request ("remove the subtitles from 5s to 9s", "add an
  illustration of a rocket at 12s with subtitles below") into edits. Claude gets a compact summary of the
  timeline in REEL seconds (blocks with keys like `g1`, `z0`, `l2`, caption lines, imported files, the
  playhead and the selection) and answers with a short list of operations: delete, remove_captions, cut,
  add_illustration, add_text, add_media, set_layout, add_zoom, move, edit, caption_style.
- The code validates every operation, converts reel time to source time (`hypercut/edit.py`) and applies
  them to a copy of the plan. Unknown or malformed operations are skipped. Keys are resolved before anything
  moves; caption removal and cuts apply last, cuts from the end backwards, so every time refers to the reel
  the user was looking at.
- New illustrations are drawn by the analyze stage's illustrator (`visuals.illustrate`), one batch per
  request; if drawing fails the beat becomes big text with its title. A new visual replaces visuals already
  in that stretch. "With subtitles below" maps to the split layout.
- The API returns the edited plan without saving it; the editor applies it as one undo step.

**Alternatives.** Letting Claude rewrite the whole plan JSON (simple, but plans are 60 to 100 KB, slow to
send back, and one slip corrupts timings or drops illustrations). Doing the request in the browser with
the user's API key (breaks ADR 0003, Claude on the subscription by default). Regex commands without Claude
(cheap but brittle for "the zoom near the start" or "the bit about breakfast").

**Consequences.** One Claude call per request (about 30 s on the subscription), plus one per batch of new
illustrations. The vocabulary is fixed, so requests outside it get "I couldn't make that change" rather than
a broken plan. Removing captions in a cold-open hook removes them in both places that span plays.
