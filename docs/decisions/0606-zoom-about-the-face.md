# 0606: Zoom about the face

Status: accepted, 2026-10-17

**Decision.** Zooms scale the speaker panel about the face point instead of the frame (or panel) center.
`ReframeKey.cy` now carries the face's height in the source frame (decision 0501's track, e.g. 0.21 to
0.35 on real footage) and `cx` the horizontal crop center (the face unless clamped at an edge). The face
point in the panel is `pointInOutput(cropRect(source, panel, cx, cy), cx, cy)`, clamped to the panel; the
transform origin is that point, and the face in output pixels is it plus the panel top. `sceneAt(plan, t)`
in `layout.ts` computes this once per frame for both the video layer and the overlays. For graphic
placement in speaker mode, `faceY = face.y / H`, because a zoom about the face does not move it. Without
reframe keys the face point is the panel center and `faceY` stays 0.4 (the old defaults).

**Alternatives.** Keep center zooms and lower cy-aware crops (the crop is already full height for
landscape sources, so the face cannot be moved to the center vertically); zoom about a fixed upper-third
point (wrong for seated or off-center subjects).

**Why.** With the face high in frame, a 1.2x center zoom pushed it up and partly out of the top: zooms
looked like they moved away from the subject, and `faceY` mispredicted where the face ended up, so
graphics could land on it.

**Consequences.** A scale of at least 1 about a point inside the panel always keeps the panel covered, so
no letterboxing (tested). Old plans with `cy = 0.5` zoom about the vertical middle, as before. Emoji bursts
are also limited to a vertical reach of 0.12H so they stay in their band and off the face.
