# 0019: Claude reviews the rendered video

Status: accepted, 2026-10-20

**Context.** Adi has been catching the same problems by eye in every test reel: graphics near the face, text cut
off, visuals that miss the point. Cardboard's agent reviews with a vision model.

**Decision.**
- `hypercut/review.py` (`review(plan, video)`, `python -m hypercut.review`, `POST /jobs/{id}/review`) samples up to 16
  frames from the latest render (each graphic's middle plus a frame every 4 s), lists what the plan has on screen
  at each, and asks Claude (with the pictures, via `ask_json(images=...)`) for problems and fixes.
- Fixes are the editor assistant's operations, limited to delete, move, edit, anchor, set_layout and
  remove_captions, and are applied with the assistant's own validation (`apply_ops`). Nothing is saved: the editor
  shows the issues with their times and an "Apply fixes" button that is one undo step.
- It runs on demand only (one Claude call with images), after a render of the saved edit.

**Alternatives.** Reviewing every render automatically (a cost on every render; Adi may not want it). Rendering
stills per frame for the review (slower; the render already exists).

**Consequences.** The review sees what was rendered, so the edit must be saved and rendered first. Problems that
need a person (a better picture) are listed without a fix.
