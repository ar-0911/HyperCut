from __future__ import annotations

from typing import Any, get_args

from hypercut import llm
from hypercut.analyze import cuts as cutting
from hypercut.analyze.visuals import merge_graphics, plan_visuals
from hypercut.plan import (
    EditPlan, Graphic, GraphicType, Hook, HookCandidate, Source, Style, Transcript, Zoom,
)

MAX_HOOKS = 3
MAX_HOOK_SECONDS = 10.0
MIN_ITEM_SECONDS = 0.3
MAX_GRAPHIC_SECONDS = 5.0
# Items per minute of source, by style setting.
GRAPHICS_PER_MIN = {"minimal": 2, "balanced": 5, "heavy": 9}
ZOOMS_PER_MIN = {"none": 0, "low": 2, "medium": 4, "high": 8}
EASES = ("linear", "ease_in_out", "snap")
ANCHORS = ("auto", "top", "center", "bottom")

SYSTEM = (
    "You are the editor of a short-form vertical video (TikTok/Reels/Shorts). "
    "You get a timed transcript and return JSON only. Never invent words that are not in the transcript."
)

PROMPT = """Transcript, one word per line as `index time word` (time in seconds):
{words}

Video length: {duration:.1f}s. Graphics theme "{theme}", density "{density}"; zoom frequency "{zoom_frequency}".

Return one JSON object:
{{
  "hooks": [  // up to 3, best first; each a 2-5 second line that makes a viewer stay
    {{"start_word": <index>, "end_word": <index, inclusive>, "score": <0..1>, "why": "<bold claim, surprising number, question, conflict, payoff tease...>"}}
  ],
  "graphics": [  // at most {max_graphics}, spread out, never overlapping
    {{"type": one of {types}, "start": <s>, "end": <s>, "props": {{}}, "anchor": "auto"|"top"|"center"|"bottom"}}
  ],
  "zooms": [  // at most {max_zooms} punch-ins on emphasised words or topic changes; 1-3 s each
    {{"start": <s>, "end": <s>, "ease": "ease_in_out"|"snap"|"linear"}}
  ]
}}
Graphic props: kinetic_text {{"text"}}; stat_card {{"value","label"}}; emoji_burst {{"emoji"}}; \
list_build {{"items": [..]}}; lower_third {{"title","subtitle"}}; progress_bar {{}}.
All times are source seconds within 0..{duration:.1f}."""


def analyze(
    transcript: Transcript,
    source: Source,
    style: Style,
    audio_wav: str | None = None,
    strategy: str = "cold_open",
    visuals: bool = False,
) -> EditPlan:
    """Fill hook, segments, graphics and zooms of an EditPlan.

    With `visuals`, also mix layouts per beat and draw an original illustration for the beats that
    get a visual (more Claude calls; see `hypercut.analyze.visuals`).
    """
    if strategy not in ("cold_open", "trim"):
        raise ValueError(f"unknown hook strategy: {strategy!r}")
    plan = EditPlan(source=source, transcript=transcript, style=style)
    words = transcript.words
    if not words:
        return plan

    minutes = source.duration / 60
    max_graphics = _cap(GRAPHICS_PER_MIN[style.graphics.density], minutes)
    max_zooms = _cap(ZOOMS_PER_MIN[style.camera.zoom_frequency], minutes)
    raw = llm.ask_json(
        PROMPT.format(
            words="\n".join(f"{i} {w.start:.2f} {w.text}" for i, w in enumerate(words)),
            duration=source.duration,
            theme=style.graphics.theme,
            density=style.graphics.density,
            zoom_frequency=style.camera.zoom_frequency,
            max_graphics=max_graphics,
            max_zooms=max_zooms,
            types=list(get_args(GraphicType)),
        ),
        system=SYSTEM,
    )

    candidates = _hooks(raw.get("hooks"), transcript, source.duration)
    plan.hook = Hook(strategy=strategy, chosen=0, candidates=candidates)
    plan.graphics = _graphics(raw.get("graphics"), source.duration, max_graphics)
    plan.zooms = _zooms(raw.get("zooms"), source.duration, max_zooms, style.camera.zoom_scale)

    silences = cutting.detect_silences(audio_wav, style.pacing.max_silence) if audio_wav else []
    cuts = cutting.cut_ranges(
        transcript, source.duration, style.pacing.max_silence, style.pacing.remove_fillers, silences
    )
    hook_span = (candidates[0].start, candidates[0].end) if candidates else None
    plan.segments = cutting.build_segments(source.duration, cuts, hook_span, strategy)
    if visuals:
        layout, art = plan_visuals(transcript, plan.segments, source.duration, style, hook_span)
        plan.layout = layout
        plan.graphics = merge_graphics(plan.graphics, art, layout)
    return plan


def _cap(per_minute: int, minutes: float) -> int:
    return 0 if per_minute == 0 else max(1, round(per_minute * minutes))


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _span(item: Any, duration: float) -> tuple[float, float] | None:
    """A valid (start, end) inside the source, or None."""
    if not isinstance(item, dict):
        return None
    start, end = _num(item.get("start")), _num(item.get("end"))
    if start is None or end is None or start < 0 or end - start < MIN_ITEM_SECONDS or end > duration + 1e-6:
        return None
    return start, min(end, duration)


def _hooks(items: Any, transcript: Transcript, duration: float) -> list[HookCandidate]:
    words = transcript.words
    out: list[HookCandidate] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        a, b, score = _num(item.get("start_word")), _num(item.get("end_word")), _num(item.get("score"))
        if a is None or b is None or a != int(a) or b != int(b):
            continue
        a, b = int(a), int(b)
        if not 0 <= a <= b < len(words):
            continue
        start, end = words[a].start, words[b].end
        if end <= start or end - start > MAX_HOOK_SECONDS or end > duration + 1e-6:
            continue
        out.append(HookCandidate(
            start=start,
            end=min(end, duration),
            text=" ".join(w.text for w in words[a : b + 1]),
            score=min(max(score if score is not None else 0.5, 0.0), 1.0),
            why=str(item.get("why", ""))[:300],
        ))
    out.sort(key=lambda c: -c.score)
    return out[:MAX_HOOKS]


def _graphics(items: Any, duration: float, limit: int) -> list[Graphic]:
    valid_types = set(get_args(GraphicType))
    out: list[Graphic] = []
    for item in items if isinstance(items, list) else []:
        span = _span(item, duration)
        if span is None or item.get("type") not in valid_types:
            continue
        start, end = span
        if item["type"] != "progress_bar":
            end = min(end, start + MAX_GRAPHIC_SECONDS)
        props = item.get("props")
        anchor = item.get("anchor")
        out.append(Graphic(
            id="",
            type=item["type"],
            start=start,
            end=end,
            props=props if isinstance(props, dict) else {},
            anchor=anchor if anchor in ANCHORS else "auto",
        ))
    out.sort(key=lambda g: g.start)
    out = out[:limit]
    for i, g in enumerate(out, 1):
        g.id = f"g{i}"
    return out


def _zooms(items: Any, duration: float, limit: int, scale: float) -> list[Zoom]:
    out: list[Zoom] = []
    for item in items if isinstance(items, list) else []:
        span = _span(item, duration)
        if span is None:
            continue
        ease = item.get("ease")
        out.append(Zoom(start=span[0], end=span[1], scale=scale, ease=ease if ease in EASES else "ease_in_out"))
    out.sort(key=lambda z: z.start)
    kept: list[Zoom] = []
    for z in out:  # zooms must not overlap
        if not kept or z.start >= kept[-1].end:
            kept.append(z)
    return kept[:limit]
