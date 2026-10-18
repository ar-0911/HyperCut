"""Place the big titles behind the speaker where the head overlaps them a little, using the cut-out.

The renderer centres a behind-the-speaker title just above the face, which is right for a medium shot but
hides it completely in a close-up. With the cut-out we can see where the speaker actually is, so each title
gets a height (`props.y`) where roughly a quarter of it is covered: it reads, and the head still clearly
passes in front of it. Where every height would hide most of it, the title goes in front instead.
See docs/decisions/0901-*.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from hypercut.plan import EditPlan, Graphic

TARGET = 0.25  # share of the title the speaker should cover
MAX_COVER = 0.5  # more than this at every height: put the title in front
STEP = 0.01
TOP, BOTTOM = 0.08, 0.6  # title centres considered, fraction of output height
SCALE = 4  # the mask is read at 1/4 size


def title_size(text: str, width: int) -> float:
    """Font size in px, as `titleSize` in render/src/Depth.tsx."""
    chars = max(1, len(text))
    return min(width * 0.36, (width * 0.92) / (chars * 0.48))


def read_alpha(matte_path: str | Path, t: float, width: int, height: int):
    """The cut-out's alpha at source time t, at 1/SCALE size (uint8 array), or None."""
    import numpy as np

    w, h = max(1, width // SCALE), max(1, height // SCALE)
    res = subprocess.run(
        ["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-ss", f"{max(0.0, t):.3f}", "-i", str(matte_path),
         "-frames:v", "1", "-vf", f"alphaextract,scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True,
    )
    if res.returncode != 0 or len(res.stdout) < w * h:
        return None
    return np.frombuffer(res.stdout[: w * h], np.uint8).reshape(h, w)


def best_y(cover_at) -> tuple[float, float]:
    """(y, coverage) of the candidate centre whose coverage is closest to TARGET (higher wins ties).
    `cover_at(y)` gives the share of the title covered with its centre at y."""
    best = None
    y = TOP
    while y <= BOTTOM + 1e-9:
        c = cover_at(y)
        key = (abs(c - TARGET), y)
        if best is None or key < best[0]:
            best = (key, round(y, 3), c)
        y += STEP
    return best[1], best[2]


def place_title(g: Graphic, plan: EditPlan, alphas: list) -> None:
    """Set `props.y` on one title from the masks sampled during it, or move it in front."""
    from hypercut.matte.cutout import face_at

    out_w, out_h = plan.output.width, plan.output.height
    text = str(g.props.get("text") or "").upper()
    size = title_size(text, out_w)
    box_h = size * 0.8 / out_h  # cap height, fraction of output height
    box_w = min(len(text) * 0.48 * size, out_w * 0.92) / out_w  # fraction of output width
    masks = [(a, face_at(plan.reframe, t)) for t, a in alphas if a is not None]
    if not masks:
        return

    def cover_at(y: float) -> float:
        worst = 0.0
        for a, face in masks:
            h, w = a.shape
            # Full-height 9:16 crop around the reframe centre: output rows are source rows.
            crop_w = min(w, h * out_w / out_h)
            cx = (face[0] if face else 0.5) * w
            left = min(max(cx - crop_w / 2, 0), w - crop_w)
            x0 = int(left + crop_w * (0.5 - box_w / 2))
            x1 = int(left + crop_w * (0.5 + box_w / 2))
            y0, y1 = int((y - box_h / 2) * h), int((y + box_h / 2) * h)
            box = a[max(0, y0):max(y0 + 1, y1), max(0, x0):max(x0 + 1, x1)]
            worst = max(worst, float((box > 127).mean()) if box.size else 0.0)
        return worst

    y, cover = best_y(cover_at)
    if cover > MAX_COVER:
        g.layer = "front"  # a close-up: behind the head it could not be read
    else:
        g.props = {**g.props, "y": y}


def place_titles(plan: EditPlan, matte_path: str | Path) -> EditPlan:
    """Give every behind-the-speaker title without a `y` its height (or move it in front). In place."""
    for g in plan.graphics:
        if g.layer != "behind" or g.type != "kinetic_text" or "y" in g.props:
            continue
        dur = g.end - g.start
        times = [g.start + dur * k for k in (0.2, 0.5, 0.8)]
        place_title(g, plan, [(t, read_alpha(matte_path, t, plan.source.width, plan.source.height)) for t in times])
    return plan
