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
# Active speaker (ADR 0506): in a shot with two or more people, the crop goes to the one whose mouth moves.
PRESENCE = 0.5  # share of a shot's samples a person must be found in to count as in the shot
ACTIVITY_WINDOW = 5  # samples (1 s at 5 fps) mouth movement is averaged over
QUIET = 0.02  # mean jaw change per sample below which nobody counts as talking
MIN_TURN = 1.5  # seconds someone must lead before the crop moves to them
SAME_FACE = 0.05  # candidates this close in one sample are the same face


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
    # How open each candidate's mouth is (0..1, MediaPipe's jawOpen), when there are two or more; None if unread.
    mouths: tuple[float | None, ...] = ()
    switch: bool = False  # the crop moves to another person here, inside the shot (ADR 0506)


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
    The hard cuts are kept as `shots`, where animated transitions can go (ADR 0613). In a shot with two or
    more people the crop follows whoever is talking and jumps to them like a cut (`switches`, ADR 0506).
    """
    half = _crop_half_width(source)
    shots = [round(d.t, 3) for i, d in enumerate(detections) if d.cut and i > 0]
    if half >= 0.5 or not any(d.cx is not None for d in detections):
        return Reframe(shots=shots)  # already vertical (or narrower), or no face: center crop
    detections = drop_outliers(follow_main_face(follow_active_speaker(detections)))
    switches = [round(d.t, 3) for d in detections if d.switch and not d.cut]

    lo, hi = half, 1 - half
    clamp = lambda x: min(max(x, lo), hi)  # noqa: E731
    face_y = lambda d: 0.5 if d.cy is None else min(max(d.cy, 0.0), 1.0)  # noqa: E731

    def first_face(i: int) -> Detection | None:
        """First detection with a face at or after sample i, within the same shot."""
        for j in range(i, len(detections)):
            if j > i and (detections[j].cut or detections[j].switch):
                return None
            if detections[j].cx is not None:
                return detections[j]
        return None

    start = first_face(0) or next(d for d in detections if d.cx is not None)
    pos, pos_y = clamp(start.cx), face_y(start)
    keys: list[ReframeKey] = []
    key = lambda t: ReframeKey(t=max(0.0, t), cx=round(pos, 4), cy=round(pos_y, 4))  # noqa: E731
    for i, d in enumerate(detections):
        if (d.cut or d.switch) and i > 0:
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
    return Reframe(keys=keys, shots=shots, switches=switches)


def _shots(detections: list[Detection], switches: bool = True) -> list[list[int]]:
    """Indices of the detections grouped by shot (a new group at each hard cut, and at each move to another
    person unless `switches` is False)."""
    shots: list[list[int]] = []
    for i, d in enumerate(detections):
        if d.cut or (switches and d.switch) or not shots:
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
            out[i] = (Detection(d.t, c[0], c[1], d.cut, d.candidates, d.mouths, d.switch) if c
                      else Detection(d.t, cut=d.cut, candidates=d.candidates, mouths=d.mouths, switch=d.switch))
    return out


def _people(detections: list[Detection], shot: list[int]) -> list[dict[int, tuple]]:
    """The people in a shot: each a track {sample index: (cx, cy, score, mouth)}, joining a sample's face to the
    track whose last position is nearest (within FOLLOW_DISTANCE). Only tracks found in PRESENCE of the shot."""
    tracks: list[dict[int, tuple]] = []
    for i in shot:
        d = detections[i]
        taken: set[int] = set()
        faces: list[tuple] = []  # the same face found in overlapping tiles counts once, at its surest
        for k, c in sorted(enumerate(d.candidates), key=lambda kc: -kc[1][2]):
            if not any(max(abs(f[0] - c[0]), abs(f[1] - c[1])) < SAME_FACE for f in faces):
                faces.append((*c, d.mouths[k] if k < len(d.mouths) else None))
        for c in faces:
            best, gap = None, FOLLOW_DISTANCE
            for n, tr in enumerate(tracks):
                last = tr[max(tr)]
                dist = max(abs(last[0] - c[0]), abs(last[1] - c[1]))
                if n not in taken and dist <= gap:
                    best, gap = n, dist
            if best is None:
                tracks.append({})
                best = len(tracks) - 1
            taken.add(best)
            tracks[best][i] = c
    return [tr for tr in tracks if len(tr) >= PRESENCE * len(shot)]


def _activity(track: dict[int, tuple], shot: list[int]) -> list[float]:
    """Mouth movement per sample of the shot: the mean absolute change in jaw opening over a short window."""
    moves = []
    prev = None
    for i in shot:
        m = track.get(i, (None,) * 4)[3]
        moves.append(abs(m - prev) if m is not None and prev is not None else 0.0)
        prev = m if m is not None else prev
    half = ACTIVITY_WINDOW // 2
    return [sum(moves[max(0, k - half) : k + half + 1]) / ACTIVITY_WINDOW for k in range(len(moves))]


def follow_active_speaker(detections: list[Detection], min_turn: float = MIN_TURN) -> list[Detection]:
    """In shots with two or more people, put the crop on whoever is talking (ADR 0506).

    Talking is read from the mouth: whoever's jaw moves most over the last second leads, and the crop moves to a
    new person only once they have led for `min_turn` seconds, so a "yeah" or a laugh doesn't flip the frame. The
    move is a jump marked `switch`, like a cut, never a pan across the table. Shots with one person, or without
    mouth readings, are left as they are.
    """
    out = list(detections)
    for shot in _shots(detections, switches=False):
        people = _people(detections, shot)
        if len(people) < 2 or not any(tr[i][3] is not None for tr in people for i in tr):
            continue
        activity = [_activity(tr, shot) for tr in people]
        dt = (detections[shot[-1]].t - detections[shot[0]].t) / max(1, len(shot) - 1) or 1 / SAMPLE_FPS
        hold = max(1, round(min_turn / dt))
        leaders = []
        for k in range(len(shot)):
            n = max(range(len(people)), key=lambda p: activity[p][k])
            leaders.append(n if activity[n][k] >= QUIET else None)
        # Whoever talks first frames the shot from its start; after that, a turn needs `hold` samples in a row.
        current = next((n for n in leaders if n is not None), None)
        if current is None:
            continue
        chosen = [current] * len(shot)
        run_start, run_who = 0, current
        for k, n in enumerate(leaders):
            if n != run_who:
                run_start, run_who = k, n
            if run_who is not None and run_who != current and k - run_start + 1 >= hold:
                current = run_who
                for j in range(run_start, k + 1):
                    chosen[j] = current
            chosen[k] = current
        for k, i in enumerate(shot):
            d, face = detections[i], people[chosen[k]].get(i)
            switch = k > 0 and chosen[k] != chosen[k - 1]
            if face is None:
                out[i] = Detection(d.t, cut=d.cut, switch=switch)
            else:
                out[i] = Detection(d.t, face[0], face[1], d.cut, (face[:3],), (face[3],), switch)
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
                out[i] = Detection(detections[i].t, cut=detections[i].cut, switch=detections[i].switch)

    for i, d in enumerate(detections):
        if (d.cut or d.switch) and shot:
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


# Face landmarks with blendshapes, for how open each mouth is when a shot has two or more people (ADR 0506).
LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)
MOUTH_CROP = 2.4  # crop side around a face, in face widths, for the landmarker
MOUTH_SIZE = 256  # px the crop is scaled to


def _model_path(url: str = MODEL_URL) -> str:
    """A MediaPipe model, downloaded once into ~/.cache/hypercut (or HYPERCUT_CACHE)."""
    import os
    import urllib.request
    from pathlib import Path

    cache = Path(os.environ.get("HYPERCUT_CACHE", Path.home() / ".cache" / "hypercut"))
    path = cache / url.rsplit("/", 1)[-1]
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(path)
    return str(path)


def _mouth_reader():
    """A function (rgb frame, faces as (cx, cy, score, area)) -> jaw openness per face (None where unread), or
    None when the landmark model can't be had: then shots with several people keep the main face."""
    try:
        import cv2
        import mediapipe as mp
        import numpy as np
        from mediapipe.tasks.python import BaseOptions, vision

        landmarker = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=_model_path(LANDMARKER_URL)),
            running_mode=vision.RunningMode.IMAGE, num_faces=1, output_face_blendshapes=True))
    except Exception as e:  # no network for the model, or an old MediaPipe
        import logging

        logging.getLogger(__name__).warning("active speaker detection is off: %s", e)
        return None

    def read(rgb, faces) -> tuple[float | None, ...]:
        h, w = rgb.shape[:2]
        out = []
        for cx, cy, _score, area in faces:
            side = int(MOUTH_CROP * (area * w * h) ** 0.5)
            x0, y0 = max(0, int(cx * w - side / 2)), max(0, int(cy * h - side / 2))
            crop = rgb[y0 : y0 + side, x0 : x0 + side]
            if crop.size == 0:
                out.append(None)
                continue
            crop = cv2.resize(crop, (MOUTH_SIZE, MOUTH_SIZE))
            result = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(crop)))
            shapes = result.face_blendshapes[0] if result.face_blendshapes else []
            jaw = next((b.score for b in shapes if b.category_name == "jawOpen"), None)
            out.append(None if jaw is None else round(float(jaw), 4))
        return tuple(out)

    read.close = landmarker.close
    return read


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
    mouths = None  # loaded the first time a frame has two or more faces (False if it can't be)
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
            found = _distinct(faces(rgb, FULL_MIN_SCORE) + _search_tiles(rgb, faces))
            best = max(found, key=lambda f: f[3], default=None)
            cands = tuple((round(cx, 4), round(cy, 4), round(score, 3)) for cx, cy, score, _ in found)
            jaws: tuple[float | None, ...] = ()
            if len(found) >= 2:
                if mouths is None:
                    mouths = _mouth_reader() or False  # False: tried, not available
                jaws = mouths(rgb, found) if mouths else ()
            out.append(Detection(t, best[0], best[1], cut, cands, jaws) if best else Detection(t, cut=cut))
    if mouths:
        mouths.close()
    return out


def _distinct(found: list[tuple]) -> list[tuple]:
    """One entry per face: overlapping tiles find the same face several times; the surest one is kept."""
    out: list[tuple] = []
    for f in sorted(found, key=lambda f: -f[2]):
        if not any(max(abs(o[0] - f[0]), abs(o[1] - f[1])) < SAME_FACE for o in out):
            out.append(f)
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
