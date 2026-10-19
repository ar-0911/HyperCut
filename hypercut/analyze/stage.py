"""Stage graphics (ADR 0611): what the speaker talks about, drawn behind the cut-out speaker, only on the
moments that call for one. Three kinds, picked per moment by the main analyze call:

- card_stack: 1-3 illustrated cards sliding out from behind the speaker, when they name things (roles,
  steps, products).
- scene: a drawn world replacing the room, the speaker pulled back a little, to set where the story is.
- chart: an animated chart behind the pulled-back speaker, only for numbers that are actually said.

Cards and scenes are drawn by the same illustrator as the layout visuals; charts are drawn by the renderer.

Without the cut-out (`style.depth.cutout`, ADR 0614) the real room stays: cards and charts are animated over
the footage beside the speaker, off the face, and there are no scenes.
"""

from __future__ import annotations

import math
from typing import Any

from hypercut.plan import STAGE_GRAPHIC_TYPES, EditPlan, Graphic, Style

STAGE_PER_MIN = 2  # at most; most reels need fewer
MAX_SECONDS = {"card_stack": 5.5, "scene": 5.0, "chart": 5.0}
MIN_SECONDS = 1.5
MAX_CARDS = 3
MAX_POINTS = 8
CHART_KINDS = ("line", "bars")

PROMPT = """,
  "stage": [  // graphics of what is said, drawn BEHIND the cut-out speaker. Use them like a professional editor: only on the moments that really call for one (most reels need 1-3, never more than {max_stage}, [] when nothing does), not overlapping each other or the "behind" titles, 2.5-5 s each
    {{"type": "card_stack", "start": <s>, "end": <s>, "cards": [{{"title": "<1-3 words, as said>", "brief": "<what to draw: a specific scene or object for this, not an icon>"}}]}},  // 1-3 cards, when the speaker names things (roles, steps, products, places)
    {{"type": "scene", "start": <s>, "end": <s>, "title": "<1-3 words>", "brief": "<a full background world for what is said: place, objects, mood; no people>"}},  // to set where or what the story is about (an intro, a topic change)
    {{"type": "chart", "start": <s>, "end": <s>, "headline": "<number + 1-2 words, e.g. 20 YEARS>", "kind": "line"|"bars", "values": [<2-8 numbers>], "labels": ["<label per value>"], "unit": "<optional unit>"}}  // only for numbers actually said; values must tell the same story
  ]"""

# The same, when the speaker is not cut out: drawn over the real footage, so no scene replacing the room.
FRONT_PROMPT = """,
  "stage": [  // graphics of what is said, animated OVER the real footage beside the speaker (never over the face; the background is not changed). Use them like a professional editor: only on the moments that really call for one (most reels need 1-3, never more than {max_stage}, [] when nothing does), not overlapping each other, 2.5-5 s each
    {{"type": "card_stack", "start": <s>, "end": <s>, "cards": [{{"title": "<1-3 words, as said>", "brief": "<what to draw: a specific scene or object for this, not an icon>"}}]}},  // 1-3 cards, when the speaker names things (roles, steps, products, places)
    {{"type": "chart", "start": <s>, "end": <s>, "headline": "<number + 1-2 words, e.g. 20 YEARS>", "kind": "line"|"bars", "values": [<2-8 numbers>], "labels": ["<label per value>"], "unit": "<optional unit>"}}  // only for numbers actually said; values must tell the same story
  ]"""


def prompt(max_stage: int, cutout: bool) -> str:
    """The stage part of the analyze prompt: behind a cut-out speaker, or over the real footage."""
    return (PROMPT if cutout else FRONT_PROMPT).format(max_stage=max_stage)


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _words(v: Any, n: int, chars: int) -> str:
    return " ".join(str(v or "").split()[:n])[:chars]


def stage_props(kind: str, item: dict) -> dict | None:
    """Clean props for a stage graphic (before drawing), or None if it has nothing to show."""
    if kind == "card_stack":
        cards = []
        for c in item.get("cards") if isinstance(item.get("cards"), list) else []:
            if isinstance(c, dict) and _words(c.get("title"), 3, 28):
                cards.append({"title": _words(c.get("title"), 3, 28), "brief": str(c.get("brief") or c.get("title"))[:400]})
        return {"cards": cards[:MAX_CARDS]} if cards else None
    if kind == "scene":
        brief = str(item.get("brief") or "").strip()
        return {"title": _words(item.get("title"), 3, 28), "brief": brief[:400]} if brief else None
    if kind == "chart":
        raw = item.get("values") if isinstance(item.get("values"), list) else []
        values = [x for x in (_num(v) for v in raw[:MAX_POINTS]) if x is not None]
        if len(values) < 2:
            return None
        labels = item.get("labels") if isinstance(item.get("labels"), list) else []
        labels = [_words(x, 2, 12) for x in labels[: len(values)]]
        return {
            "headline": _words(item.get("headline"), 3, 24),
            "kind": item.get("kind") if item.get("kind") in CHART_KINDS else "line",
            "values": values,
            "labels": labels + [""] * (len(values) - len(labels)),
            "unit": _words(item.get("unit"), 1, 8),
        }
    return None


def parse_stage(items: Any, duration: float, limit: int, cutout: bool = True) -> list[Graphic]:
    """Valid, non-overlapping stage graphics from Claude's answer, capped in length and number. Without the
    cut-out there are no scenes: they would replace the room."""
    out: list[Graphic] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or item.get("type") not in STAGE_GRAPHIC_TYPES:
            continue
        if item["type"] == "scene" and not cutout:
            continue
        start, end = _num(item.get("start")), _num(item.get("end"))
        if start is None or end is None or start < 0 or end - start < MIN_SECONDS or start >= duration:
            continue
        props = stage_props(item["type"], item)
        if props is None:
            continue
        kind = item["type"]
        out.append(Graphic(id="", type=kind, start=start, end=min(end, duration, start + MAX_SECONDS[kind]), props=props))
    out.sort(key=lambda g: g.start)
    kept: list[Graphic] = []
    for g in out:
        if not kept or g.start >= kept[-1].end:
            kept.append(g)
    return kept[:limit]


def add_stage(plan: EditPlan, stage: list[Graphic]) -> None:
    """Give each stage graphic its moment, in place: the speaker fills the frame there (a split or full-frame
    visual under it makes way, as in the AI box), and big titles or effects behind the speaker at the same
    time are dropped, so one thing happens at once."""
    from hypercut import edit

    for i, g in enumerate(stage, 1):
        g.id = f"s{i}"
    for g in stage:
        edit.clear_visuals(plan, g.start, g.end, keep="")
        edit.set_layout(plan, g.start, g.end, "speaker")
    clash = lambda g: (g.layer == "behind" or g.type in ("orbit", "fly_out", "particles")) and any(  # noqa: E731
        g.start < s.end and s.start < g.end for s in stage)
    plan.graphics = sorted([g for g in plan.graphics if not clash(g)] + stage, key=lambda g: g.start)


def _palette(style: Style) -> str:
    g = style.graphics
    return f"Palette: {g.accent_color}, {g.secondary_color or g.accent_color}, {g.panel_color} and soft neutrals."


def draw_stage(graphics: list[Graphic], style: Style, draw=None) -> bool:
    """Draw the cards and scenes that have no art yet (props.layers), in place. Cards that fail to draw keep
    their title and the renderer shows a plain card. True if anything was drawn."""
    from hypercut.analyze import visuals

    draw = draw or visuals.illustrate
    palette = _palette(style)
    cards = [c for g in graphics if g.type == "card_stack" for c in g.props.get("cards") or []
             if isinstance(c, dict) and c.get("brief") and not c.get("layers")]
    scenes = [g for g in graphics if g.type == "scene" and g.props.get("brief") and not g.props.get("layers")]
    changed = False
    if cards:
        for card, art in zip(cards, draw([f"{c['brief']}. {palette} Fill the canvas: no frame, no text." for c in cards])):
            if art:
                card.update(art)
                changed = True
    if scenes:
        briefs = [f"{g.props['brief']}. {palette} Soft depth, slightly muted so a person in front stands out." for g in scenes]
        for g, art in zip(scenes, draw(briefs, visuals.PORTRAIT_VIEWBOX, visuals.PORTRAIT)):
            if art:
                g.props = {**g.props, **art}
                changed = True
    return changed
