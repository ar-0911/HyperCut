# 0505: Find small faces in tiles and follow each shot's main face

Status: accepted, 2026-10-18

**Decision.** Detection per sample is the whole frame (score at least 0.5) plus full-height square tiles
across the frame (score at least 0.7, half-height tiles only if those find nothing), and every face found
is kept as a candidate. Per shot, each candidate seeds a track (nearest candidate in each sample, within
0.15 of the frame), and the track with the highest total score wins, the higher one on a tie. A running
median then drops stray points. Cuts are checked on every frame, not every sample, and the first frame of a
new shot is always sampled. A shot with no face is framed on its centre.

**Alternatives.** The full-range MediaPipe model (not in the Tasks API bundle we use). The largest face per
frame (what we did: it picked a patterned shirt and gesturing hands). A median filter alone (fails when a
false face appears in every frame of a shot).

**Why.** In the montage test, speakers sitting in wide 16:9 shots were too small for the short-range model,
so the crop held the previous shot's position or followed a false face and showed a shoulder or a wall.
With these changes every shot sampled every 4 s of the test clip is framed on the speaker.

**Consequences.** About 4 detector runs per sample instead of 1 (the 70 s test clip took 41 s). The
track choice is per shot, so in a two-shot the crop stays on the more confident face; it does not switch
to whoever is talking.
