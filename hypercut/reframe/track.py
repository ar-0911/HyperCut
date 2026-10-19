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
FULL_MIN_SCORE = 0.5  # detector confidence needed for a face found in the whole frame
TILE_MIN_SCORE = 0.7  # detector confidence needed for a face found in a zoomed-in window
OUTLIER_WINDOW = 7  # samples (within a shot) in the running median that outlier faces are judged by
OUTLIER_DISTANCE = 0.1  # fraction of source width a detection may sit from that median
FOLLOW_DISTANCE = 0.15  # how far the main face may move between samples and still be the same person


@dataclass(frozen=True)
class Detection:
    """Largest face at time `t` (source seconds). cx/cy are normalized 0..1; None means no face."""

    t: float
    cx: float | None = None
    cy: float | None = None
    cut: bool = False  # a new shot starts at this sample (hard cut in the source)
    # Every face the detector found here as (cx, cy, score); cx/cy above is one of them. Empty when the
    # detector reports only one face, as fakes in tests do.
    candidates: tuple[tuple[float, float, float], ...] = ()


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
    The hard cuts are kept as `shots`, where animated transitions can go (ADR 0613).
    """
    half = _crop_half_width(source)
    shots = [round(d.t, 3) for i, d in enumerate(detections) if d.cut and i > 0]
    if half >= 0.5 or not any(d.cx is not None for d in detections):
        return Reframe(shots=shots)  # already vertical (or narrower), or no face: center crop
    detections = drop_outliers(follow_main_face(detections))

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
            # A shot with no face at all (a title card, B-roll) is framed on its centre rather than on
            # wherever the previous speaker happened to sit.
            nxt = first_face(i)
            keys.append(key(d.t - 0.001))
            pos, pos_y = (clamp(nxt.cx), face_y(nxt)) if nxt is not None else (clamp(0.5), 0.5)
        elif d.cx is not None:
            target = clamp(d.cx)
            if abs(target - pos) > dead_zone:
                pos += alpha * (target - pos)
            target_y = face_y(d)
            if abs(target_y - pos_y) > dead_zone:
                pos_y += alpha * (target_y - pos_y)
        keys.append(key(d.t))
    return Reframe(keys=keys, shots=shots)


def _shots(detections: list[Detection]) -> list[list[int]]:
    """Indices of the detections grouped by shot (a new group at each hard cut)."""
    shots: list[list[int]] = []
    for i, d in enumerate(detections):
        if d.cut or not shots:
            shots.append([])
        shots[-1].append(i)
    return shots


def _follow(cands: list[tuple], k: int, seed: tuple) -> list[tuple | None]:
    """The track through a shot's candidates that starts at `seed` in sample k: each sample (forwards and
    backwards from k) takes the candidate nearest the previous pick, if one is near enough."""
    picks: list[tuple | None] = [None] * len(cands)
    picks[k] = seed
    for order in (range(k + 1, len(cands)), range(k - 1, -1, -1)):
        pos = seed
        for i in order:
            near = [c for c in cands[i] if abs(c[0] - pos[0]) <= FOLLOW_DISTANCE and abs(c[1] - pos[1]) <= FOLLOW_DISTANCE]
            if near:
                pos = picks[i] = min(near, key=lambda c: (c[0] - pos[0]) ** 2 + (c[1] - pos[1]) ** 2)
    return picks


def follow_main_face(detections: list[Detection]) -> list[Detection]:
    """In each shot, follow the face that is there most surely and most often, not whichever face-like
    thing is biggest in a given frame (a patterned shirt, gesturing hands, a second person walking past).

    Every candidate seeds a track through the shot (nearest candidate in each sample, so a speaker who
    moves is still followed); the track with the highest total score wins, the higher one on a tie since
    faces sit above bodies (ADR 0505).
    """
    out = list(detections)
    for shot in _shots(detections):
        cands = [detections[i].candidates for i in shot]
        best: list[tuple | None] | None = None
        best_key = None
        for k, cs in enumerate(cands):
            for seed in cs:
                picks = _follow(cands, k, seed)
                found = [c for c in picks if c is not None]
                key = (round(sum(c[2] for c in found), 6), -sum(c[1] for c in found) / len(found))
                if best_key is None or key > best_key:
                    best, best_key = picks, key
        if best is None:
            continue
        for i, c in zip(shot, best):
            d = detections[i]
            out[i] = Detection(d.t, c[0], c[1], d.cut, d.candidates) if c else Detection(d.t, cut=d.cut, candidates=d.candidates)
    return out


def drop_outliers(detections: list[Detection]) -> list[Detection]:
    """Forget detections far from the running median of their shot (a headlight or a poster read as a
    face for a sample or two), so the crop stays on the person who is there all along (ADR 0505)."""
    out = list(detections)
    shot: list[int] = []

    def flush() -> None:
        xs = [(i, detections[i].cx) for i in shot if detections[i].cx is not None]
        for k, (i, cx) in enumerate(xs):
            lo, hi = max(0, k - OUTLIER_WINDOW // 2), k + OUTLIER_WINDOW // 2 + 1
            window = sorted(x for _, x in xs[lo:hi])
            median = window[len(window) // 2]
            if abs(cx - median) > OUTLIER_DISTANCE:
                out[i] = Detection(detections[i].t, cut=detections[i].cut)

    for i, d in enumerate(detections):
        if d.cut and shot:
            flush()
            shot = []
        shot.append(i)
    flush()
    return out


def _sample_frames(video_path: str, sample_fps: float) -> Iterator[tuple[float, object, bool]]:
    """Yield (t, frame, cut) for sampled frames; cut marks a hard cut since the previous sample.

    Every frame is checked for a cut (a tiny histogram), and the first frame of a new shot is always
    sampled, so the crop snaps on the exact frame the shot changes rather than up to a sample later.
    """
    import cv2  # optional dependency

    cap = cv2.VideoCapture(video_path)
    prev_hist = None
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, round(fps / sample_fps))
        index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            small = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([small], [0, 1], None, [32, 32], [0, 180, 0, 256])
            cv2.normalize(hist, hist)
            cut = prev_hist is not None and cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL) < CUT_THRESHOLD
            prev_hist = hist
            if cut or index % step == 0:
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
    import numpy as np
    from mediapipe.tasks.python import BaseOptions, vision

    options = vision.FaceDetectorOptions(
        base_options=BaseOptions(model_asset_path=_model_path()),
        running_mode=vision.RunningMode.IMAGE,
        min_detection_confidence=FULL_MIN_SCORE,
    )
    out: list[Detection] = []
    with vision.FaceDetector.create_from_options(options) as fd:
        def faces(rgb, min_score: float = 0.0) -> list[tuple[float, float, float, float]]:
            """(cx, cy, score, area) of each face scoring at least `min_score`, normalized to `rgb`."""
            h, w = rgb.shape[:2]
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
            out = []
            for d in fd.detect(image).detections:
                score = d.categories[0].score if d.categories else 1.0
                if score < min_score:
                    continue
                b = d.bounding_box
                out.append(((b.origin_x + b.width / 2) / w, (b.origin_y + b.height / 2) / h, score, b.width * b.height / (w * h)))
            return out

        for t, frame, cut in _sample_frames(video_path, sample_fps):
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            found = faces(rgb, FULL_MIN_SCORE) + _search_tiles(rgb, faces)
            best = max(found, key=lambda f: f[3], default=None)
            cands = tuple((round(cx, 4), round(cy, 4), round(score, 3)) for cx, cy, score, _ in found)
            out.append(Detection(t, best[0], best[1], cut, cands) if best else Detection(t, cut=cut))
    return out


def tiles(width: int, height: int) -> list[list[tuple[int, int, int]]]:
    """Square windows (x, y, side) to search for faces too small for the detector in the full frame
    (the short-range model sees a 128 px image, so a seated speaker in a wide 16:9 shot is a few pixels).
    Two passes: squares the frame's height across the width, then half-height squares over its top three
    quarters, where faces are. Neighbours overlap so a face on a seam is whole in one of them."""
    passes = []
    for side, rows in ((height, 1), (height // 2, 2)):
        if side < 64:
            continue
        n = max(1, -(-2 * width // side) - 1)  # ~50% overlap
        xs = [round(i * (width - side) / max(1, n - 1)) for i in range(n)] if width > side else [0]
        ys = [0] if rows == 1 else [0, height // 4]
        passes.append([(x, y, side) for y in ys for x in xs])
    return passes


def _search_tiles(rgb, faces) -> list[tuple[float, float, float, float]]:
    """Faces (cx, cy, score, area) found in the tiles of the first pass that finds any, in full-frame
    coordinates. The full-height pass runs on every sample: the short-range model often misses a seated
    speaker in the whole 16:9 frame yet finds them surely in a square around them."""
    h, w = rgb.shape[:2]
    for windows in tiles(w, h):
        found = []
        for x, y, side in windows:
            # Zoomed-in windows see more face-like texture, so they need a surer detection.
            for cx, cy, score, area in faces(rgb[y : y + side, x : x + side], TILE_MIN_SCORE):
                found.append(((x + cx * side) / w, (y + cy * side) / h, score, area * side * side / (w * h)))
        if found:
            return found
    return []


def reframe(video_path: str, source: Source, *, detector: Detector | None = None) -> Reframe:
    """Face-tracked crop keys for `video_path`. Pass `detector` to inject detections."""
    # Skip decoding entirely when no horizontal motion is possible.
    if _crop_half_width(source) >= 0.5:
        return Reframe()
    detections = (detector or detect_faces)(video_path, source, SAMPLE_FPS)
    return smooth_track(detections, source)
