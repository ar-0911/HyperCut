"""Plan edits addressed in REEL time (seconds of the finished short), for the editor's assistant.

The plan stores everything on the source timeline; people talk about what they see in the reel. These
helpers convert between the two through `segments` and apply edits to a copy of the plan. Pure functions:
no I/O, no Claude.
"""

from __future__ import annotations

from dataclasses import dataclass

from hypercut.plan import BackgroundSpan, EditPlan, Graphic, LayoutSpan, Segment, Zoom

# Graphics that fill the split panel or the whole frame; only one shows well at a time.
VISUAL_TYPES = {"illustration", "kinetic_text", "stat_card", "list_build", "media", "motion"}

EPS = 1e-6
MIN_SPAN = 0.1


@dataclass
class Piece:
    """One kept segment placed on the reel: source [start, end) plays from reel second `out`, at `speed`."""

    index: int
    start: float
    end: float
    out: float
    speed: float = 1.0

    @property
    def out_end(self) -> float:
        return self.reel(self.end)

    def reel(self, t: float) -> float:
        """Reel second at which source second t (inside this piece) plays."""
        return self.out + (t - self.start) / self.speed

    def source(self, r: float) -> float:
        """Source second shown at reel second r (inside this piece)."""
        return self.start + (r - self.out) * self.speed


def pieces(plan: EditPlan) -> list[Piece]:
    segs = plan.segments or [Segment(start=0, end=plan.source.duration)]
    speed = plan.style.pacing.speed
    out, cursor = [], 0.0
    for i, s in enumerate(segs):
        out.append(Piece(i, s.start, s.end, cursor, speed))
        cursor += (s.end - s.start) / speed
    return out


def reel_duration(plan: EditPlan) -> float:
    return plan.output_duration()


def to_reel(plan: EditPlan, t: float) -> list[float]:
    """Every reel time a source time plays at (two for a cold-open hook, none if cut)."""
    return [p.reel(t) for p in pieces(plan) if p.start - EPS <= t < p.end - EPS]


def first_reel(plan: EditPlan, start: float, end: float) -> tuple[float, float] | None:
    """Where a source span first shows in the reel, clipped to the piece it starts in."""
    for p in pieces(plan):
        a, b = max(start, p.start), min(end, p.end)
        if b > a + EPS:
            return p.reel(a), p.reel(b)
    return None


def to_source(plan: EditPlan, t: float) -> tuple[float, int]:
    """The source time shown at reel time t, and the index of its piece. Clamped to the reel."""
    ps = pieces(plan)
    t = min(max(t, 0.0), ps[-1].out_end)
    for p in ps:
        if t < p.out_end - EPS:
            return p.source(t), p.index
    last = ps[-1]
    return last.end, last.index


def source_span(plan: EditPlan, start: float, end: float) -> tuple[float, float]:
    """A reel span as a source span. If the reel span crosses into a piece that plays earlier source (the
    jump after a cold-open hook), it is cut at the end of the piece it starts in."""
    a, ia = to_source(plan, start)
    b, ib = to_source(plan, max(end, start + MIN_SPAN))
    piece = pieces(plan)[ia]
    if ib != ia and b <= a + EPS:
        b = piece.end
    if ib == ia and b <= a:
        b = min(piece.end, a + MIN_SPAN)
    b = min(b, plan.source.duration)
    if b - a < MIN_SPAN:
        a = max(0.0, b - MIN_SPAN)
    return round(a, 3), round(b, 3)


def _overlaps_reel(plan: EditPlan, start: float, end: float, a: float, b: float) -> bool:
    """Does any reel occurrence of source span [start, end) overlap reel [a, b)?"""
    for p in pieces(plan):
        s, e = max(start, p.start), min(end, p.end)
        if e > s + EPS:
            ra, rb = p.reel(s), p.reel(e)
            if rb > a + EPS and ra < b - EPS:
                return True
    return False


def remove_captions(plan: EditPlan, a: float, b: float) -> int:
    """Drop the caption words shown between reel times a and b. Returns how many went."""
    before = len(plan.transcript.words)
    plan.transcript.words = [
        w for w in plan.transcript.words if not _overlaps_reel(plan, (w.start + w.end) / 2 - EPS, (w.start + w.end) / 2 + EPS, a, b)
    ]
    return before - len(plan.transcript.words)


def cut(plan: EditPlan, a: float, b: float) -> float:
    """Remove reel [a, b) from the short (splitting segments). Returns the seconds removed."""
    kept: list[Segment] = []
    removed = 0.0
    for p, seg in zip(pieces(plan), plan.segments or [Segment(start=0, end=plan.source.duration)]):
        lo, hi = max(a, p.out), min(b, p.out_end)
        if hi <= lo + EPS:
            kept.append(seg)
            continue
        removed += hi - lo
        left = (p.start, p.source(lo))
        right = (p.source(hi), p.end)
        for s, e in (left, right):
            if e - s >= 0.05:
                kept.append(Segment(start=round(s, 3), end=round(e, 3), reason=seg.reason))
    if not kept:
        raise ValueError("that would cut the whole video")
    plan.segments = kept
    return removed


def set_layout(plan: EditPlan, start: float, end: float, mode: str) -> None:
    """Make source [start, end) use `mode`, trimming or splitting the spans it overlaps."""
    out: list[LayoutSpan] = []
    for span in plan.layout:
        if span.end <= start + EPS or span.start >= end - EPS:
            out.append(span)
            continue
        if span.start < start - EPS:
            out.append(LayoutSpan(start=span.start, end=start, mode=span.mode))
        if span.end > end + EPS:
            out.append(LayoutSpan(start=end, end=span.end, mode=span.mode))
    if mode != "speaker":
        out.append(LayoutSpan(start=start, end=end, mode=mode))
    plan.layout = sorted(out, key=lambda s: s.start)


def set_background(plan: EditPlan, start: float, end: float, new: BackgroundSpan) -> None:
    """Make source [start, end) use background `new`, trimming or splitting the spans it overlaps."""
    out: list[BackgroundSpan] = []
    for span in plan.backgrounds:
        if span.end <= start + EPS or span.start >= end - EPS:
            out.append(span)
            continue
        if span.start < start - EPS:
            out.append(span.model_copy(update={"end": start}))
        if span.end > end + EPS:
            out.append(span.model_copy(update={"start": end}))
    out.append(new.model_copy(update={"start": start, "end": end}))
    plan.backgrounds = sorted(out, key=lambda s: s.start)


def new_id(plan: EditPlan, prefix: str) -> str:
    used = {g.id for g in plan.graphics}
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


def add_graphic(plan: EditPlan, type_: str, start: float, end: float, props: dict, prefix: str = "a") -> Graphic:
    g = Graphic(id=new_id(plan, prefix), type=type_, start=start, end=end, props=props)
    plan.graphics = sorted([*plan.graphics, g], key=lambda x: x.start)
    return g


def add_zoom(plan: EditPlan, start: float, end: float, scale: float) -> Zoom:
    z = Zoom(start=start, end=end, scale=min(max(scale, 1.0), 2.0))
    plan.zooms = sorted([*plan.zooms, z], key=lambda x: x.start)
    return z


def clear_visuals(plan: EditPlan, start: float, end: float, keep: str) -> list[str]:
    """Make room for a new visual over source [start, end): visuals mostly under it go, others are trimmed
    back. Returns the ids removed."""
    removed, out = [], []
    for g in plan.graphics:
        if g.id == keep or g.type not in VISUAL_TYPES or g.end <= start + EPS or g.start >= end - EPS:
            out.append(g)
            continue
        overlap = min(g.end, end) - max(g.start, start)
        before, after = start - g.start, g.end - end
        if overlap >= 0.5 * (g.end - g.start) or max(before, after) < MIN_SPAN * 5:
            removed.append(g.id)
            continue
        if before >= after:
            g.end = start
        else:
            g.start = end
        out.append(g)
    plan.graphics = out
    return removed


# Word-accurate edits (ADR 0021): "remove the pause before the second answer" or "cut the sentence about
# pricing" land on word boundaries instead of wherever a rounded reel second falls.

PAUSE_MIN = 0.3  # a gap between words shorter than this is not a pause anyone asks to remove


@dataclass
class ReelWord:
    start: float  # reel seconds
    end: float
    text: str
    piece: int


def reel_words(plan: EditPlan) -> list[ReelWord]:
    """Caption words as they play in the reel (a word in the hook and the body shows twice), in reel order."""
    out = []
    for p in pieces(plan):
        for w in plan.transcript.words:
            mid = (w.start + w.end) / 2
            if p.start - EPS <= mid < p.end - EPS:
                out.append(ReelWord(p.reel(max(w.start, p.start)), p.reel(min(w.end, p.end)), w.text, p.index))
    return sorted(out, key=lambda w: w.start)


def pauses(plan: EditPlan, minimum: float = PAUSE_MIN) -> list[tuple[float, float]]:
    """Reel spans between consecutive words of the same piece longer than `minimum` (cuts already removed
    the gaps between pieces)."""
    ws = reel_words(plan)
    return [(a.end, b.start) for a, b in zip(ws, ws[1:]) if a.piece == b.piece and b.start - a.end > minimum]


def pause_near(plan: EditPlan, t: float, side: str = "nearest", within: float = 3.0) -> tuple[float, float] | None:
    """The pause the viewer sits through just before what starts at reel second t (side "before"), just
    after what ends there ("after"), or the nearest one; None if none is within `within` seconds."""
    gaps = pauses(plan)
    if side == "before":
        gaps = [g for g in gaps if g[1] <= t + 0.5 and t - g[1] <= within]
        return max(gaps, key=lambda g: g[1]) if gaps else None
    if side == "after":
        gaps = [g for g in gaps if g[0] >= t - 0.5 and g[0] - t <= within]
        return min(gaps, key=lambda g: g[0]) if gaps else None
    dist = lambda g: 0.0 if g[0] <= t <= g[1] else min(abs(t - g[0]), abs(t - g[1]))  # noqa: E731
    gaps = [g for g in gaps if dist(g) <= within]
    return min(gaps, key=dist) if gaps else None


def pause_cut(plan: EditPlan, gap: tuple[float, float], keep: float | None = None) -> tuple[float, float] | None:
    """The reel span to remove so a pause shrinks to `keep` seconds on each side (default: the style's)."""
    keep = plan.style.pacing.keep_pause if keep is None else keep
    a, b = gap[0] + keep, gap[1] - keep
    return (a, b) if b - a >= 0.05 else None


def word_cut(plan: EditPlan, start: float, end: float) -> tuple[float, float] | None:
    """Reel span covering exactly the words whose middle falls in reel [start, end), from just after the
    word before them to just before the word after them (keeping the style's pause), so no word is clipped."""
    ws = reel_words(plan)
    inside = [i for i, w in enumerate(ws) if start - EPS <= (w.start + w.end) / 2 < end + EPS]
    if not inside:
        return None
    first, last = ws[inside[0]], ws[inside[-1]]
    keep = plan.style.pacing.keep_pause
    lo, hi = first.start, last.end
    if inside[0] > 0 and ws[inside[0] - 1].piece == first.piece:
        lo = max(ws[inside[0] - 1].end + keep, (ws[inside[0] - 1].end + first.start) / 2)
        lo = min(lo, first.start)
    if inside[-1] + 1 < len(ws) and ws[inside[-1] + 1].piece == last.piece:
        hi = min(ws[inside[-1] + 1].start - keep, (last.end + ws[inside[-1] + 1].start) / 2)
        hi = max(hi, last.end)
    return (round(lo, 3), round(hi, 3)) if hi - lo >= 0.05 else None
