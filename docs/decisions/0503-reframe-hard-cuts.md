# 0503: The crop jumps at hard cuts instead of easing

Status: accepted, 2026-10-17

**Decision.** While sampling frames, reframe compares HSV colour histograms of consecutive samples; a
correlation below 0.5 marks a hard cut. At a cut the crop snaps to the first face in the new shot (looking
ahead within the shot if the first sample has none) and holds the old position until 1 ms before the cut,
so the renderer's interpolation between keys never glides across it.

**Alternatives.** FFmpeg `select='gt(scene,x)'` in a separate pass (decodes the video twice); leaving
smoothing as is.

**Why.** Adi's first real clip is a montage of several speakers with 17 hard cuts. With smoothing only, the
crop lagged after every cut and spent most of each shot sliding toward the new speaker, often cutting them
off.

**Consequences.** Cut detection costs a tiny histogram per sampled frame. Cuts are found at the sampling
rate (every 0.2 s), so a crop can sit on the old position for up to one sample into the new shot.
