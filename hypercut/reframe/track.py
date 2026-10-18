"""Sampling, face detection and smoothing. See docs/decisions/0501-reframe-smoothing.md."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator

from hypercut.plan import Reframe, ReframeKey, Source

SAMPLE_FPS = 5.0
ALPHA = 0.25  # exponential smoothing weight of the newest target
DEAD_ZONE = 0.04  # fraction of source width the face may drift before the crop follows
TARGET_ASPECT = 9 / 16
CUT_THRESHOLD = 0.5  # histogram correlation between samples below this means a hard cut


@dataclass(frozen=True)
class Detection:
    """Largest face at time `t` (source seconds). cx/cy are normalized 0..1; None means no face."""

    t: float
    cx: float | None = None
    cy: float | None = None
    cut: bool = False  # a new shot starts at this sample (hard cut in the source)


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
    once the target leaves the dead zone around it, then eases toward it exponentially. At a
    hard cut (`Detection.cut`) it jumps straight to the new shot's face (ADR 0503).
    cx is clamped so the crop window never leaves the frame. cy is the face's own height in the
    frame (smoothed the same way): the full-height crop never moves vertically, so the renderer
    uses it only to zoom in on the face and keep graphics off it (ADR 0504).
    """
    half = _crop_half_width(source)
    if half >= 0.5 or not any(d.cx is not None for d in detections):
        return Reframe()  # already vertical (or narrower), or no face: center crop

    lo, hi = half, 1 - half
    clamp = lambda x: min(max(x, lo), hi)  # noqa: E731
    face_y = lambda d: 0.5 if d.cy is None else min(max(d.cy, 0.0), 1.0)  # noqa: E731

    def first_face(i: int) -> Detection | None:
        """First detection with a face at or after sample i, within the same shot."""
        for j in range(i, len(detections)):
            if j > i and detections[j].cut:
                return None
            if detections[j].cx is not None:
                return detections[j]
        return None

    start = first_face(0) or next(d for d in detections if d.cx is not None)
    pos, pos_y = clamp(start.cx), face_y(start)
    keys: list[ReframeKey] = []
    key = lambda t: ReframeKey(t=max(0.0, t), cx=round(pos, 4), cy=round(pos_y, 4))  # noqa: E731
    for i, d in enumerate(detections):
        if d.cut and i > 0:
            # Snap to the new shot's speaker instead of easing across the cut, and hold the old
            # position right up to the cut so interpolation between keys can't glide over it.
            nxt = first_face(i)
            if nxt is not None:
                keys.append(key(d.t - 0.001))
                pos, pos_y = clamp(nxt.cx), face_y(nxt)
        elif d.cx is not None:
            target = clamp(d.cx)
            if abs(target - pos) > dead_zone:
                pos += alpha * (target - pos)
            target_y = face_y(d)
            if abs(target_y - pos_y) > dead_zone:
                pos_y += alpha * (target_y - pos_y)
        keys.append(key(d.t))
    return Reframe(keys=keys)


def _sample_frames(video_path: str, sample_fps: float) -> Iterator[tuple[float, object, bool]]:
    """Yield (t, frame, cut) for sampled frames; cut marks a hard cut since the previous sample."""
    import cv2  # optional dependency

    cap = cv2.VideoCapture(video_path)
    prev_hist = None
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, round(fps / sample_fps))
        index = 0
        while cap.grab():
            if index % step == 0:
                ok, frame = cap.retrieve()
                if ok:
                    small = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2HSV)
                    hist = cv2.calcHist([small], [0, 1], None, [32, 32], [0, 180, 0, 256])
                    cv2.normalize(hist, hist)
                    cut = prev_hist is not None and cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL) < CUT_THRESHOLD
                    prev_hist = hist
                    yield index / fps, frame, cut
            index += 1
    finally:
        cap.release()


MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
)


def _model_path() -> str:
    """The MediaPipe face model, downloaded once into ~/.cache/hypercut (or HYPERCUT_CACHE)."""
    import os
    import urllib.request
    from pathlib import Path

    cache = Path(os.environ.get("HYPERCUT_CACHE", Path.home() / ".cache" / "hypercut"))
    path = cache / "blaze_face_short_range.tflite"
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.replace(path)
    return str(path)


def detect_faces(video_path: str, source: Source, sample_fps: float = SAMPLE_FPS) -> list[Detection]:
    """Real detector: largest MediaPipe face per sampled frame. Needs the `reframe` extra.

    Uses the MediaPipe Tasks API; the legacy `mp.solutions` API is gone from the
    releases that support Python 3.13 (see ADR 0502).
    """
    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    options = vision.FaceDetectorOptions(
        base_options=BaseOptions(model_asset_path=_model_path()),
        running_mode=vision.RunningMode.IMAGE,
        min_detection_confidence=0.5,
    )
    out: list[Detection] = []
    with vision.FaceDetector.create_from_options(options) as fd:
        for t, frame, cut in _sample_frames(video_path, sample_fps):
            h, w = frame.shape[:2]
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            boxes = [d.bounding_box for d in fd.detect(image).detections]
            if not boxes:
                out.append(Detection(t, cut=cut))
                continue
            b = max(boxes, key=lambda b: b.width * b.height)
            out.append(Detection(t, (b.origin_x + b.width / 2) / w, (b.origin_y + b.height / 2) / h, cut))
    return out


def reframe(video_path: str, source: Source, *, detector: Detector | None = None) -> Reframe:
    """Face-tracked crop keys for `video_path`. Pass `detector` to inject detections."""
    # Skip decoding entirely when no horizontal motion is possible.
    if _crop_half_width(source) >= 0.5:
        return Reframe()
    detections = (detector or detect_faces)(video_path, source, SAMPLE_FPS)
    return smooth_track(detections, source)
