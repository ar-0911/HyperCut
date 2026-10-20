# 0615: Moving stills, generated clips, credits, graphic colours and an overlays-only render

Status: accepted, 2026-10-20

**Decision.**
- A still picture plays like a shot: `props.move` is `push_in` (default), `pull_out`, `pan_left`, `pan_right` or
  `rise`, eased and always scaled past the frame (`stillTransform`). Analyze alternates them.
- A `media` graphic without `src` (a request not fetched yet) draws nothing.
- A motion graphic with `src` plays that clip full screen under its serif title instead of the 3D scene.
- A picture whose licence needs it (`credit_required`, CC BY) shows its credit small in the corner.
- A graphic may carry its own colour (`props.accent`, a hex colour) over the reel's accent; the editor sets it.
- `overlaysOnly` composition prop and `render --overlays 1`: graphics and captions alone on transparency as ProRes
  4444, for the editor export (0017).

**Consequences.** True depth parallax on stills (separating foreground and background) is not done; the moves
are 2D.
