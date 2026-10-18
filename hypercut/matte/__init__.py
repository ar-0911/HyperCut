"""Matte stage: cut the speaker out of every frame, for green-screen effects.

Entry point: `matte(video_path, source, reframe, out_path) -> Path`. Writes a VP9 WebM with an alpha
channel, frame for frame with the normalized video: the speaker's own pixels where the speaker is, fully
transparent elsewhere. The renderer lays it over the background and anything placed behind the speaker.
CLI: `python -m hypercut.matte VIDEO`. Needs the `matte` extra. See docs/decisions/0901-*.
"""

from hypercut.matte.cutout import MATTE_FILE, matte, needs_matte, refine
from hypercut.matte.titles import place_titles

__all__ = ["MATTE_FILE", "matte", "needs_matte", "place_titles", "refine"]
