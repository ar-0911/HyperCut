"""Sampling, face detection and smoothing. See docs/decisions/0501-reframe-smoothing.md."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator

from hypercut.plan import Reframe, ReframeKey, Source

SAMPLE_FPS = 5.0
ALPHA = 0.25  # exponential smoothing weight of the newest target
DEAD_ZONE = 0.04  # fraction of source width the face may drift before the crop follows
TARGET_ASPECT = 9 / 16


@dataclass(frozen=True)
class Detection:
    """Largest face at time `t` (source seconds). cx/cy are normalized 0..1; None means no face."""

    t: float
    cx: float | None = None
    cy: float | None = None


Detector = Callable[[str, Source, float], list[Detection]]


def _crop_half_width(source: Source) -> float:
    """Half the crop width as a fraction of source width (full-height 9:16 crop)."""
    return min(1.0, (source.height * TARGET_ASPECT) / source.width) / 2


def smooth_track(
    detections: list[Detection],
    source: Source,
    *,
    alpha: float = ALPHA,
    dead_zone: float = DEAD_ZONE,
) -> Reframe:
    """Turn raw detections into smoothed keys. Pure, so tests can feed fake detections.

    Gaps hold the last known position (leading gaps take the first one). The crop only moves
    once the target leaves the dead zone around it, then eases toward it exponentially.
    Centers are clamped so the crop window never leaves the frame. cy stays 0.5 because the
    crop uses the full source height.
    """
    half = _crop_half_width(source)
    if half >= 0.5 or not any(d.cx is not None for d in detections):
        return Reframe()  # already vertical (or narrower), or no face: center crop

    lo, hi = half, 1 - half
    first = next(d.cx for d in detections if d.cx is not None)
    pos = min(max(first, lo), hi)
    keys: list[ReframeKey] = []
    for d in detections:
        if d.cx is not None:
            target = min(max(d.cx, lo), hi)
            if abs(target - pos) > dead_zone:
                pos += alpha * (target - pos)
        keys.append(ReframeKey(t=max(0.0, d.t), cx=round(pos, 4), cy=0.5))
    return Reframe(keys=keys)


def _sample_frames(video_path: str, sample_fps: float) -> Iterator[tuple[float, object]]:
    import cv2  # optional dependency

    cap = cv2.VideoCapture(video_path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, round(fps / sample_fps))
        index = 0
        while cap.grab():
            if index % step == 0:
                ok, frame = cap.retrieve()
                if ok:
                    yield index / fps, frame
            index += 1
    finally:
        cap.release()


def detect_faces(video_path: str, source: Source, sample_fps: float = SAMPLE_FPS) -> list[Detection]:
    """Real detector: largest MediaPipe face per sampled frame. Needs the `reframe` extra."""
    import cv2
    import mediapipe as mp

    out: list[Detection] = []
    with mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5) as fd:
        for t, frame in _sample_frames(video_path, sample_fps):
            result = fd.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            faces = [d.location_data.relative_bounding_box for d in (result.detections or [])]
            if not faces:
                out.append(Detection(t))
                continue
            b = max(faces, key=lambda b: b.width * b.height)
            out.append(Detection(t, b.xmin + b.width / 2, b.ymin + b.height / 2))
    return out


def reframe(video_path: str, source: Source, *, detector: Detector | None = None) -> Reframe:
    """Face-tracked crop keys for `video_path`. Pass `detector` to inject detections."""
    # Skip decoding entirely when no horizontal motion is possible.
    if _crop_half_width(source) >= 0.5:
        return Reframe()
    detections = (detector or detect_faces)(video_path, source, SAMPLE_FPS)
    return smooth_track(detections, source)
