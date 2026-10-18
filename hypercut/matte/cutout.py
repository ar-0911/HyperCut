"""Person segmentation, mask cleanup and the transparent cut-out video. See docs/decisions/0901-*."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Callable

from hypercut.plan import EditPlan, Reframe, Source

log = logging.getLogger(__name__)

MATTE_FILE = "matte.webm"
# Width of the frames the segmentation models see (they work at 256 px, so more only costs time) and
# of the mask FFmpeg scales up to the video's size.
SEGMENT_WIDTH = 640
# Person probability mapped to opacity: below LOW is background, above HIGH is the speaker.
LOW, HIGH = 0.35, 0.75
# Width of the frames the edge is finished at: the model's mask is snapped to the picture's real edges
# (hair, shoulders) at this size, and FFmpeg scales the result up to the video's size.
EDGE_WIDTH = 1280
GUIDE_RADIUS, GUIDE_EPS = 6, 1e-3  # guided filter: how far an edge may move, how strongly it follows the image
CHOKE = (0.2, 0.85)  # opacity ramp after snapping: trims the faint rim of old background around the speaker
HAIR_SIZE = 512  # short side of the frames the hair matting model sees
SMOOTH = 0.6  # weight of the newest mask in the running average that stops edges flickering
CUT_IOU = 0.6  # masks overlapping less than this between frames: a hard cut, don't average across it

MODELS = {
    # Multi-class (hair, body, clothes...): clean silhouettes but held objects count as background.
    "multiclass": "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
    "selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite",
    # Plain person/background: keeps what the person holds, but bleeds into busy backgrounds.
    "selfie": "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
    "selfie_segmenter/float16/latest/selfie_segmenter.tflite",
    # MODNet portrait matting (Apache-2.0): a real alpha matte with hair strands, used for the edge only.
    "modnet.onnx": "https://huggingface.co/Xenova/modnet/resolve/main/onnx/model.onnx",
}

# (rgb frame, as a numpy array) -> (person probability from the multi-class model, from the selfie model)
Segmenter = Callable[[object], tuple[object, object]]


def needs_matte(plan: EditPlan) -> bool:
    """Whether the plan uses green-screen effects, so the render needs the cut-out video."""
    return plan.style.depth.enabled


def _model_path(name: str) -> str:
    """A MediaPipe segmentation model, downloaded once into ~/.cache/hypercut (or HYPERCUT_CACHE)."""
    import urllib.request

    cache = Path(os.environ.get("HYPERCUT_CACHE", Path.home() / ".cache" / "hypercut"))
    path = cache / (name if name.endswith(".onnx") else Path(MODELS[name]).name)
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(MODELS[name], tmp)
        tmp.replace(path)
    return str(path)


def mediapipe_segmenter() -> Segmenter:
    """Both MediaPipe models on one frame. Needs the `matte` extra."""
    import mediapipe as mp
    import numpy as np
    from mediapipe.tasks.python import BaseOptions, vision

    def make(name: str):
        return vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=_model_path(name)), output_confidence_masks=True))

    multi, selfie = make("multiclass"), make("selfie")

    def segment(rgb):
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        person = 1.0 - multi.segment(image).confidence_masks[0].numpy_view()  # class 0 is background
        held = selfie.segment(image).confidence_masks[0].numpy_view()
        return np.squeeze(person).astype(np.float32), np.squeeze(held).astype(np.float32)

    # Closed by `matte` when done; left to the garbage collector, MediaPipe complains at interpreter exit.
    segment.close = lambda: (multi.close(), selfie.close())  # type: ignore[attr-defined]
    return segment


# (rgb frame) -> alpha 0..1 at the model's own size, any size: the speaker's fine edge (hair)
HairMatter = Callable[[object], object]


def modnet_matter() -> HairMatter | None:
    """MODNet on one frame, or None when onnxruntime or the model can't be had (the cut-out then uses the
    snapped MediaPipe edge alone)."""
    try:
        import cv2
        import numpy as np
        import onnxruntime as ort

        session = ort.InferenceSession(_model_path("modnet.onnx"), providers=["CPUExecutionProvider"])
    except Exception as e:  # noqa: BLE001 - optional quality upgrade, never a reason to fail the matte
        log.warning("hair matting unavailable (%s); using the segmentation edge", e)
        return None

    def matte_hair(rgb):
        h, w = rgb.shape[:2]
        k = HAIR_SIZE / min(h, w)
        size = (max(32, round(w * k / 32) * 32), max(32, round(h * k / 32) * 32))
        x = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA).astype(np.float32) / 127.5 - 1.0
        return session.run(None, {"input": x.transpose(2, 0, 1)[None]})[0][0, 0]

    return matte_hair


def refine(person, held, face: tuple[float, float] | None, prev=None):
    """Turn raw model output (low resolution, 0..1) into the speaker's mask at the same resolution.

    - Keeps only the person at `face` (normalized x, y; the reframe's main face), so the other people in
      a shot don't get cut out with the speaker; without a face, the largest person.
    - Adds back what the speaker holds (a book, a phone): the selfie model's pixels inside the convex
      hull of the speaker's silhouette. Outside it the selfie model tends to bleed into the background.
    - Averages with the previous frame's mask (`prev`) unless the shot changed, so edges don't flicker.
    Returns a float32 array in 0..1.
    """
    import cv2
    import numpy as np

    h, w = person.shape
    solid = (person > 0.5).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(solid, connectivity=8)
    if n <= 1:
        mask = np.zeros_like(person, dtype=np.float32)
    else:
        keep = None
        if face is not None:
            fx = min(w - 1, max(0, int(face[0] * w)))
            fy = min(h - 1, max(0, int(face[1] * h)))
            keep = labels[fy, fx] or None
            if keep is None:  # the face point fell just outside: nearest blob by its bounding box
                def dist(i: int) -> float:
                    x, y, bw, bh = stats[i, :4]
                    dx = max(x - fx, 0, fx - (x + bw))
                    dy = max(y - fy, 0, fy - (y + bh))
                    return dx * dx + dy * dy
                keep = min(range(1, n), key=dist)
        if keep is None:
            keep = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        region = labels == keep
        hull = np.zeros((h, w), np.uint8)
        pts = cv2.findNonZero(region.astype(np.uint8))
        cv2.fillConvexPoly(hull, cv2.convexHull(pts), 1)
        # The kept person's soft edge (its probability near the blob) plus held objects inside the hull.
        near = cv2.dilate(region.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        mask = np.where(near, person, 0).astype(np.float32)
        mask = np.maximum(mask, np.where(hull > 0, held, 0).astype(np.float32))
    return smooth(mask, prev)


def same_shot(mask, prev) -> bool:
    """Whether two consecutive masks overlap enough to be the same shot (no hard cut between them)."""
    import numpy as np

    if prev is None or prev.shape != mask.shape:
        return False
    a, b = prev > 0.5, mask > 0.5
    union = np.logical_or(a, b).sum()
    return bool(np.logical_and(a, b).sum() / union >= CUT_IOU) if union else True


def smooth(mask, prev, shot: bool | None = None):
    """Average with the previous frame's mask within a shot, so edges don't flicker; not across a cut."""
    if prev is None or prev.shape != mask.shape:
        return mask
    return SMOOTH * mask + (1 - SMOOTH) * prev if (same_shot(mask, prev) if shot is None else shot) else mask


def with_hair(hair, mask):
    """The hair matte (any size) limited to the kept speaker and filled with the speaker's solid body.

    MODNet draws hair and soft edges well but can miss a body part or catch another person; MediaPipe's
    `mask` (from `refine`) says who the speaker is and where the body is. Returns 0..1 at the hair's size.
    """
    import cv2
    import numpy as np

    h, w = hair.shape
    m = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
    grow = max(3, round(w / 36)) | 1
    near = cv2.dilate((m > 0.3).astype(np.uint8), np.ones((grow, grow), np.uint8)).astype(np.float32)
    near = np.clip(cv2.GaussianBlur(near, (0, 0), grow / 4) * 1.5, 0, 1)
    core = cv2.erode((m > 0.6).astype(np.uint8), np.ones((9, 9), np.uint8)).astype(np.float32)
    return np.maximum(np.clip(hair, 0, 1) * near, cv2.GaussianBlur(core, (0, 0), 3))


def guided_filter(guide, src, radius: int, eps: float):
    """He et al.'s guided filter: `src` smoothed so its edges follow the edges of the gray `guide` (0..1)."""
    import cv2

    box = lambda x: cv2.boxFilter(x, -1, (2 * radius + 1, 2 * radius + 1))  # noqa: E731
    mi, mp_ = box(guide), box(src)
    a = (box(guide * src) - mi * mp_) / (box(guide * guide) - mi * mi + eps)
    b = mp_ - a * mi
    return box(a) * guide + box(b)


def snap_edge(rgb, alpha):
    """Fit a soft alpha (0..1, any size) to the real edges of `rgb` and trim the faint rim of old
    background around it. Returns 8-bit alpha at `rgb`'s size."""
    import cv2
    import numpy as np

    h, w = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    a = cv2.resize(alpha.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
    a = guided_filter(gray, a, GUIDE_RADIUS, GUIDE_EPS)
    lo, hi = CHOKE
    return (np.clip((a - lo) / (hi - lo), 0.0, 1.0) * 255 + 0.5).astype(np.uint8)


def face_at(reframe: Reframe, t: float) -> tuple[float, float] | None:
    """The main face (normalized x, y) at source time `t`, interpolated from the reframe keys.

    x is the crop center, which sits on the face except near the frame edges (where `refine` falls back
    to the nearest person); y is the face height (0.5 in plans older than ADR 0504).
    """
    keys = reframe.keys
    if not keys:
        return None
    if t <= keys[0].t:
        return keys[0].cx, keys[0].cy
    for a, b in zip(keys, keys[1:]):
        if t < b.t:
            k = (t - a.t) / (b.t - a.t) if b.t > a.t else 1.0
            return a.cx + (b.cx - a.cx) * k, a.cy + (b.cy - a.cy) * k
    return keys[-1].cx, keys[-1].cy


def to_alpha(mask):
    """Soft speaker mask -> 8-bit alpha at the same (low) resolution, with a slightly tightened edge.

    FFmpeg scales it up to the video's size when merging, which also smooths the edge.
    """
    import numpy as np

    return (np.clip((mask - LOW) / (HIGH - LOW), 0.0, 1.0) * 255 + 0.5).astype(np.uint8)


def matte(
    video_path: str | Path,
    source: Source,
    reframe: Reframe,
    out_path: str | Path,
    *,
    segmenter: Segmenter | None = None,
    hair: HairMatter | None | bool = True,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Write the speaker cut-out of `video_path` (the normalized video) to `out_path` as VP9 WebM with alpha.

    FFmpeg decodes a copy EDGE_WIDTH wide. MediaPipe finds the speaker on a smaller copy, MODNet (`hair`;
    True loads it, False or None skips it) draws the hair, and the edge is snapped to the picture at
    EDGE_WIDTH. FFmpeg scales that alpha up and merges it with the untouched full-size frames.
    """
    import cv2
    import numpy as np

    segment = segmenter or mediapipe_segmenter()
    matte_hair = modnet_matter() if hair is True else (hair or None)
    w, h = source.width, source.height
    # Python never touches a full-resolution frame: the models need small pictures, and FFmpeg merges the
    # alpha with the full-size original.
    ew = min(w, EDGE_WIDTH)
    eh = max(2, round(h * ew / w / 2) * 2)
    mw = min(ew, SEGMENT_WIDTH)
    mh = max(2, round(h * mw / w / 2) * 2)
    out_path = Path(out_path)
    tmp = out_path.with_suffix(".part.webm")
    decode = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(video_path), "-vf", f"scale={ew}:{eh}:flags=area",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE,
    )
    encode = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video_path),
         "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{ew}x{eh}", "-r", f"{source.fps:g}", "-i", "-",
         "-filter_complex", f"[1:v]scale={w}:{h}:flags=bicubic[a];[0:v][a]alphamerge,format=yuva420p",
         "-an", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "30", "-deadline", "realtime", "-cpu-used", "8",
         "-row-mt", "1", "-auto-alt-ref", "0", str(tmp)],
        stdin=subprocess.PIPE,
    )
    frame_bytes = ew * eh * 3
    total = max(1, round(source.duration * source.fps))
    prev = soft = None
    i = 0
    ok = False
    try:
        while True:
            buf = decode.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            rgb = np.frombuffer(buf, np.uint8).reshape(eh, ew, 3)
            small = cv2.resize(rgb, (mw, mh), interpolation=cv2.INTER_AREA) if (mw, mh) != (ew, eh) else rgb
            person, held = segment(small)
            mask = refine(person, held, face_at(reframe, i / source.fps), prev)
            shot = same_shot(mask, prev)
            prev = mask
            if matte_hair is not None:
                new = with_hair(matte_hair(rgb), mask)
                soft = smooth(new, soft, shot) if soft is not None and soft.shape == new.shape else new
            else:
                soft = to_alpha(mask).astype(np.float32) / 255
            encode.stdin.write(snap_edge(rgb, soft).tobytes())
            i += 1
            if on_progress and i % 30 == 0:
                on_progress(min(1.0, i / total))
        ok = True
    finally:
        decode.stdout.close()
        encode.stdin.close()
        decode.wait()
        encode.wait()
        if not ok:
            tmp.unlink(missing_ok=True)
        if segmenter is None:
            segment.close()  # type: ignore[attr-defined]
    if decode.returncode != 0 or encode.returncode != 0 or i == 0 or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"matte failed after {i} frames (ffmpeg exit {decode.returncode}/{encode.returncode})")
    tmp.replace(out_path)
    return out_path
