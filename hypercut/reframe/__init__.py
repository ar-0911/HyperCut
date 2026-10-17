"""Reframe stage: face track -> smoothed 9:16 crop-center keys.

Entry point: `reframe(video_path, source) -> Reframe`. CLI: `python -m hypercut.reframe VIDEO`.
"""

from hypercut.reframe.track import Detection, reframe, smooth_track

__all__ = ["Detection", "reframe", "smooth_track"]
