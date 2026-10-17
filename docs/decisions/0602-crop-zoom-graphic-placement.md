# 0602: Crop, zoom and keeping graphics off the face

Status: accepted, 2026-10-17

**Decision.**
- *Crop.* Scale the source to cover 1080x1920, then slide so the interpolated `reframe` center is central,
  clamped to the frame edges. Keys are interpolated linearly in source time and held at the ends; no keys
  means a center crop. The smoothing is the reframe stage's job (ADR 0501+); the renderer does not smooth.
- *Zoom.* A CSS scale about the output frame center (where the crop puts the speaker). `snap` reaches full
  scale in 80 ms, `linear` ramps across the span, `ease_in_out` ramps over min(0.3 s, half the span) at each
  end. Overlapping zooms take the strongest.
- *Placement.* Graphics sit in one of three vertical bands (top 14%, center 50%, bottom 70% of the height).
  `placeGraphic` honors the plan's `anchor` unless that band is within 28% of the face center or within 18%
  of the caption position; otherwise it takes the free band furthest from the face. If no band is free it
  still avoids the face before it avoids captions. The face position is the reframe center projected through
  the crop and zoom. `progress_bar` hugs the top edge and is exempt. With no reframe keys the face is
  assumed at 40% of the height.

**Alternatives.** Free-form pixel anchors in the plan; per-frame collision search; hiding graphics when
nothing is free.

**Why.** Three bands keep layouts predictable and the logic testable as a pure function; Claude only picks
a coarse anchor, which is all the schema carries. Dropping a graphic is worse than a tight fit.

**Consequences.** Treating `reframe` as the face center is an assumption of the schema (it says "crop
center"); if reframe later centers on something else, the face estimate drifts. Bands are tuned for
talking-head framing, not for a speaker filling the whole frame.
