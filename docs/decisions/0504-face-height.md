# 0504: Reframe keys carry the face's height

Status: accepted, 2026-10-17

**Decision.** `ReframeKey.cy` is the tracked face's vertical position in the source frame. It is smoothed
with the same dead zone and easing as `cx`, and it snaps at hard cuts. `cx` keeps its meaning: the
horizontal crop center, clamped to the frame.

**Alternatives.** Keep `cy` at 0.5 (the old behaviour). Add a separate face field to the plan.

**Why.** The full-height crop never moves vertically, so `cy` was a constant. The renderer read it as
"the face is mid-frame", so zooms pushed in on the frame center and drifted off faces, which sit near
the top third. Graphics placed "away from the face" also landed on the real face. Filling the existing
field fixes both without a schema change, and old plans with 0.5 render as before.

**Consequences.** Face tracking must be re-run for old jobs to get the fix. Any consumer that treated `cy` as
a crop center sees no difference: the crop is clamped vertically anyway.
