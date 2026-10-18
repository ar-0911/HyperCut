"""Person segmentation, mask cleanup and the transparent cut-out video. See docs/decisions/0901-*."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable

from hypercut.plan import EditPlan, Reframe, Source

MATTE_FILE = "matte.webm"
# Width of the frames the segmentation models see (they work at 256 px, so more only costs time) and
# of the mask FFmpeg scales up to the video's size.
SEGMENT_WIDTH = 640
# Person probability mapped to opacity: below LOW is background, above HIGH is the speaker.
LOW, HIGH = 0.35, 0.75
SMOOTH = 0.6  # weight of the newest mask in the running average that stops edges flickering
CUT_IOU = 0.6  # masks overlapping less than this between frames: a hard cut, don't average across it

MODELS = {
    # Multi-class (hair, body, clothes...): clean silhouettes but held objects count as background.
    "multiclass": "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
    "selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite",
    # Plain person/background: keeps what the person holds, but bleeds into busy backgrounds.
    "selfie": "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
    "selfie_segmenter/float16/latest/selfie_segmenter.tflite",
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
    path = cache / Path(MODELS[name]).name
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
    if prev is not None and prev.shape == mask.shape:
        a, b = prev > 0.5, mask > 0.5
        union = np.logical_or(a, b).sum()
        iou = np.logical_and(a, b).sum() / union if union else 1.0
        if iou >= CUT_IOU:
            mask = SMOOTH * mask + (1 - SMOOTH) * prev
    return mask


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
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Write the speaker cut-out of `video_path` (the normalized video) to `out_path` as VP9 WebM with alpha.

    FFmpeg decodes a small copy for the models; the mask (at that size) is piped back to FFmpeg, which
    scales it up and merges it as the alpha channel of the untouched full-size frames.
    """
    import cv2
    import numpy as np

    segment = segmenter or mediapipe_segmenter()
    w, h = source.width, source.height
    # The models only need a small picture, and FFmpeg merges the mask with the full-size original, so
    # Python never touches a full-resolution frame.
    mw = min(w, SEGMENT_WIDTH)
    mh = max(2, round(h * mw / w / 2) * 2)
    out_path = Path(out_path)
    tmp = out_path.with_suffix(".part.webm")
    decode = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(video_path), "-vf", f"scale={mw}:{mh}:flags=area",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE,
    )
    encode = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video_path),
         "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{mw}x{mh}", "-r", f"{source.fps:g}", "-i", "-",
         "-filter_complex", f"[1:v]scale={w}:{h}:flags=bicubic[a];[0:v][a]alphamerge,format=yuva420p",
         "-an", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34", "-deadline", "realtime", "-cpu-used", "8",
         "-row-mt", "1", "-auto-alt-ref", "0", str(tmp)],
        stdin=subprocess.PIPE,
    )
    frame_bytes = mw * mh * 3
    total = max(1, round(source.duration * source.fps))
    prev = None
    i = 0
    ok = False
    try:
        while True:
            buf = decode.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            rgb = np.frombuffer(buf, np.uint8).reshape(mh, mw, 3)
            person, held = segment(rgb)
            prev = refine(person, held, face_at(reframe, i / source.fps), prev)
            alpha = cv2.resize(to_alpha(prev), (mw, mh), interpolation=cv2.INTER_LINEAR)
            encode.stdin.write(alpha.tobytes())
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
