# 0608: Speed, crossfades, end fades and bundled fonts in the renderer

Status: accepted, 2026-10-18

**Decision.** `buildTimeline` takes `pacing.speed`: each segment lasts `duration / speed` frames, the
video plays with `playbackRate = speed` (audio is pitch-preserved by the browser), and overlays read the
source time as before. Imported clips keep normal speed. Transitions:
- `hard`: plain cuts, with a 3-frame audio ease at each edge so cuts do not click.
- `smooth`: each segment's sequence runs `length` seconds past its end and fades out over the next one
  (a crossfade), skipped where the next segment continues the same source.
- `zoom`: every other segment is punched in by 8%, which hides a jump cut.

`fade_in` and `fade_out` draw a black overlay at the start and end, and the last segment's audio fades
with it. Caption fonts are latin woff2 files from Fontsource committed in `render/src/font-files/` (about
400 KB, OFL/Apache, licences alongside), loaded with `FontFace` under a `delayRender`, with the nearest
available weight. A font that fails to load falls back instead of failing the render.

**Alternatives.** `@remotion/transitions` (it shortens the timeline by the overlap, which would shift every
overlay against the plan's mapping). `@remotion/google-fonts`, which downloads from fonts.gstatic.com at
render time: the first test render failed offline, and an unreachable font hangs a frame.

**Why.** Fonts must not depend on the network: renders run on the user's machine or a locked-down server. Overlapping sequences keep the reel length and every overlay time exactly as the plan says, and
the same code runs in the browser preview.

**Consequences.** During a crossfade two video frames are decoded at once, so smooth renders are a little
slower. Fonts other than the ten listed fall back to Montserrat.
