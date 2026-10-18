# 0607: Rendering imported pictures and clips

Status: accepted, 2026-10-18

**Decision.**
- `media` graphics (ADR 0012) are drawn by the composition, not by a graphic template, because a clip needs
  the output timeline to play smoothly. In split mode they fill the top panel at its final size (the slide-in
  reveals them rather than squashing them); in visual mode they fill the frame. Other visuals at the same
  time draw on top.
- Pictures use Remotion's `Img` with a slow push-in (scale 1.02 to 1.08 over the block).
- Clips use `OffthreadVideo`, muted, inside a `Sequence` per run from `mediaRuns(tl, span)`: output stretches
  where the block is on screen without a jump back in source time. Pieces that follow each other in the output
  (body segments with a filler cut between them) join one run, so B-roll plays straight through small cuts
  instead of skipping; the cold-open copy is its own run. A block longer than its clip holds the last frame
  (`Freeze`).
- `CompositionProps` gains optional `assetBase`: the browser preview fetches imported files from the API
  (`/jobs/{id}/files/`); the final render leaves it out and reads them as static files. `render.ts` links
  every `media` file into the bundle's public folder from the video's folder or `--assets DIR`, refusing names
  with path parts.

**Alternatives.** Timing clips by source time like other overlays (a filler cut every second or so would make
B-roll stutter). Pre-compositing B-roll with FFmpeg (fast, but the preview would no longer match the render).

**Consequences.** Clips must be web-playable; the API re-encodes them to H.264 (ADR 0702). Checked with a
real render of the v2 reel with an imported clip and picture.
