"""hypercut.analyze: transcript + style -> hook, segments, graphics, zooms.

One Claude call proposes hooks, graphics and zooms; plain code validates them,
decides the cuts and assembles the segments. See docs/decisions/0401-*.
"""

from hypercut.analyze.analyze import analyze

__all__ = ["analyze"]
