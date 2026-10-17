# 0502: Face detection uses the MediaPipe Tasks API

Status: accepted, 2026-10-17

**Decision.** `detect_faces` uses MediaPipe's Tasks `FaceDetector` with the BlazeFace short-range model.
The model is downloaded once from storage.googleapis.com into `~/.cache/hypercut` (override with
`HYPERCUT_CACHE`).

**Alternatives.** Pin an old MediaPipe that still has `mp.solutions` (no release supports Python 3.13);
OpenCV Haar cascades (not shipped in `opencv-python-headless`, and much less accurate); OpenCV YuNet
(its model download host was blocked where we tested).

**Why.** The first real-footage run crashed: MediaPipe 0.10.30+ removed the legacy `solutions` API that
ADR 0501's code used. The Tasks API is the supported replacement.

**Consequences.** First run needs network access to storage.googleapis.com. On Linux servers MediaPipe needs
the EGL runtime (`apt install libegl1`); desktops already have it.
