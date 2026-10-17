# 0501: Reframe sampling, smoothing and clamping

Status: accepted, 2026-10-17

**Decision.**
- Sample ~5 frames/s with OpenCV (`grab()` every frame, `retrieve()` only on sampled ones), detect the largest
  face with MediaPipe face detection (`model_selection=1`, confidence 0.5).
- Detection is a swappable `Detector` callable returning `Detection(t, cx, cy)` lists; smoothing (`smooth_track`)
  is pure. Tests inject fake detections and never import mediapipe.
- Smoothing: exponential (alpha 0.25) behind a dead zone (0.04 of source width). The crop holds still until the
  face leaves the zone, then eases toward it. Frames without a face hold the last position.
- Keys are clamped so the full-height 9:16 window stays inside the frame; `cy` is always 0.5.
- No face anywhere, or a source already 9:16 or narrower, gives empty keys (center crop) and skips decoding.
- One key per sample (about 900 for 3 min), not pruned; the renderer interpolates linearly.

**Alternatives.** Kalman filter (more tuning, little visible gain at 5 Hz); median filter (adds lag, no
dead zone); pruning keys (smaller JSON but more code and risk for the renderer); detecting every frame (5x+ cost).

**Consequences.** Constants are module-level and easy to tune. Multi-speaker footage follows the largest face,
which may flip between people. Cuts in `segments` are not considered: keys live on the source timeline and the
renderer maps them, so the crop may glide across a cut. mediapipe >= 0.10 with the legacy `solutions` API is
required by the `reframe` extra.
