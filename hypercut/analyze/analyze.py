from __future__ import annotations

from typing import Any

from hypercut import llm
from hypercut.analyze import cuts as cutting
from hypercut.analyze import cutaways, motion, stage
from hypercut.analyze.visuals import merge_graphics, plan_visuals
from hypercut.generate import available as available_assets
from hypercut.plan import (
    AROUND_GRAPHIC_TYPES, GENERATED_GRAPHIC_TYPES, BackgroundSpan, EditPlan, Graphic, Hook, HookCandidate, Source, Style, Transcript, Zoom,
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
BEHIND_PER_MIN = 3  # big titles behind the speaker per minute, with green-screen effects on
PARTICLE_KINDS = ("sparkles", "bokeh", "confetti", "embers")
MAX_AROUND_SECONDS = {"orbit": 6.0, "fly_out": 3.5, "particles": 12.0}
# Never a plain colour or gradient behind the speaker (ADR 0613): Claude only picks among the real background.
BACKGROUNDS = ("original", "blur", "dim")

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
  ],
{motion}  "ending": {{"word": <index of the last word to keep>, "why": "<...>"}}  // where the video should end: \
the last word of a complete sentence that lands as a conclusion (a payoff, a recommendation, a call to action), \
never a trailing fragment, a half sentence or a line cut off by the recording
}}
Graphic props: kinetic_text {{"text"}}; stat_card {{"value","label"}}; list_build {{"items": [..]}}; lower_third {{"title","subtitle"}}; progress_bar {{}}.
All times are source seconds within 0..{duration:.1f}."""

# Added to the prompt only when the style asks for green-screen effects (ADR 0901).
DEPTH_PROMPT = """

Green-screen effects are on: the speaker is cut out of the frame, so things can sit behind them.
Also return these keys in the same object:
  "behind": [  // at most {max_behind} big titles placed BEHIND the speaker's head, for the hook and the biggest moments (a number, a bold claim); 1-3 words each, 1.5-4 s, not overlapping other graphics
    {{"start": <s>, "end": <s>, "text": "<1-3 words>"}}
  ],
  "backgrounds": [  // optional stretches where the background changes, for emphasis; the rest stays "{background}"
    {{"start": <s>, "end": <s>, "kind": "original"|"blur"|"dim"}}
  ]{stage}"""

# Without the cut-out (ADR 0614) the real background stays as filmed and graphics are animated over it, in the
# free space beside the speaker.
OVER_PROMPT = """

The real background stays as filmed: graphics are animated over the footage where there is free space beside
the speaker, never over their face, and nothing goes behind the speaker.
Also return these keys in the same object:
  "behind": []{stage}"""


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
    depth = style.depth.enabled
    # Only a cut-out speaker can have things behind them or a different background (ADR 0614).
    cutout = depth and style.depth.cutout
    max_behind = _cap(BEHIND_PER_MIN, minutes) if cutout and style.depth.behind_titles else 0
    # Cards and charts of what is said: behind a cut-out speaker, otherwise over the real footage beside them.
    max_stage = _cap(stage.STAGE_PER_MIN, minutes) if style.depth.around else 0
    max_motion = _cap(motion.MOTION_PER_MIN, minutes)
    stage_prompt = stage.prompt(max_stage, cutout) if max_stage else ""
    if cutout:
        extra = DEPTH_PROMPT.format(max_behind=max_behind, background=style.depth.background, stage=stage_prompt)
    else:
        extra = OVER_PROMPT.format(stage=stage_prompt) if stage_prompt else ""
    raw = llm.ask_json(
        PROMPT.format(
            words="\n".join(f"{i} {w.start:.2f} {w.text}" for i, w in enumerate(words)),
            duration=source.duration,
            theme=style.graphics.theme,
            density=style.graphics.density,
            zoom_frequency=style.camera.zoom_frequency,
            max_graphics=max_graphics,
            max_zooms=max_zooms,
            types=list(GENERATED_GRAPHIC_TYPES),
            motion=motion.PROMPT.format(max_motion=max_motion),
        ) + extra,
        system=SYSTEM,
    )

    candidates = _hooks(raw.get("hooks"), transcript, source.duration)
    plan.hook = Hook(strategy=strategy, chosen=0, candidates=candidates)
    plan.graphics = _graphics(raw.get("graphics"), source.duration, max_graphics)
    plan.zooms = _zooms(raw.get("zooms"), source.duration, max_zooms, style.camera.zoom_scale)

    silences = cutting.detect_silences(audio_wav, style.pacing.max_silence) if audio_wav else []
    cuts = cutting.cut_ranges(
        transcript, source.duration, style.pacing.max_silence, style.pacing.remove_fillers, silences,
        keep_pause=style.pacing.keep_pause,
    )
    hook_span = (candidates[0].start, candidates[0].end) if candidates else None
    plan.segments = cutting.build_segments(source.duration, cuts, hook_span, strategy)
    ending = raw.get("ending")
    preferred = _num(ending.get("word")) if isinstance(ending, dict) else None
    last = cutting.ending_word(transcript, int(preferred) if preferred is not None and preferred == int(preferred) else None)
    if last is not None:
        plan.segments = cutting.end_at(plan.segments, transcript, last)
    # Stock footage and generated pictures / clips, only for what this machine is set up to fetch (ADR 0016).
    sources = available_assets()
    if visuals:
        layout, art = plan_visuals(transcript, plan.segments, source.duration, style, hook_span, sources=sources)
        plan.layout = layout
        plan.graphics = merge_graphics(plan.graphics, art, layout)
    if cutout:
        plan.backgrounds = _backgrounds(raw.get("backgrounds"), source.duration)
        plan.graphics = add_behind(plan.graphics, _behind(raw.get("behind"), source.duration, max_behind), plan.layout)
    if max_stage:
        stage.add_stage(plan, stage.parse_stage(raw.get("stage"), source.duration, max_stage, cutout))
        stage.draw_stage(plan.graphics, style)
    # A few seconds of full-screen motion graphics (ADR 0612), then one more call designs their scenes.
    moments = motion.parse_motion(raw.get("motion"), source.duration, max_motion)
    if moments:
        motion.add_motion(plan, moments)
        motion.design_scenes(plan.graphics, transcript, style)
        if "video" in sources:  # a generated clip plays instead of the 3D scene, which stays as the fallback
            motion.ask_for_clips(plan, moments)
    # Visuals next to a jump cut straddle it, like B-roll laid over the cut (ADR 0614).
    cutaways.cover_cuts(plan)
    return plan


def around_props(kind: str, item: dict) -> dict | None:
    """Clean props for an effect around the speaker, or None if it has nothing to show."""
    if kind == "particles":
        k = item.get("kind")
        return {"kind": k if k in PARTICLE_KINDS else "sparkles"}
    items = item.get("items")
    items = [" ".join(str(x).split()[:3])[:24] for x in items if str(x).strip()] if isinstance(items, list) else []
    return {"items": items[:5]} if items else None


def draw_around(graphics: list[Graphic], style: Style, draw=None) -> bool:
    """Draw the orbit and fly-out items that have no graphic yet into `props.art` ({item text: {"viewBox",
    "body"}}), in place. Keyed by the text, so an item renamed in the editor is drawn again; a failed drawing
    stays missing and the renderer falls back to a built-in icon or the word. True if anything was drawn."""
    from hypercut.analyze.visuals import draw_icons

    def missing(g: Graphic) -> list[str]:
        art = g.props.get("art") if isinstance(g.props.get("art"), dict) else {}
        return [str(x) for x in g.props.get("items") or [] if str(x).strip() and str(x) not in art]

    need = [g for g in graphics if g.type in ("orbit", "fly_out") and missing(g)]
    names = sorted({n for g in need for n in missing(g)})
    if not names:
        return False
    drawn = dict(zip(names, (draw or draw_icons)(names, style.graphics.accent_color)))
    changed = False
    for g in need:
        art = dict(g.props.get("art") or {}) if isinstance(g.props.get("art"), dict) else {}
        for n in missing(g):
            if drawn.get(n):
                art[n] = drawn[n]
                changed = True
        g.props = {**g.props, "art": art}
    return changed


def _around(items: Any, duration: float, limit: int) -> list[Graphic]:
    out: list[Graphic] = []
    for item in items if isinstance(items, list) else []:
        span = _span(item, duration)
        kind = item.get("type") if isinstance(item, dict) else None
        if span is None or kind not in AROUND_GRAPHIC_TYPES:
            continue
        props = around_props(kind, item)
        if props is None:
            continue
        start, end = span
        out.append(Graphic(id="", type=kind, start=start, end=min(end, start + MAX_AROUND_SECONDS[kind]), props=props))
    out.sort(key=lambda g: g.start)
    kept: list[Graphic] = []
    for g in out:
        if not kept or g.start >= kept[-1].end:
            kept.append(g)
    return kept[:limit]


def add_around(graphics: list[Graphic], around: list[Graphic], layout: list) -> list[Graphic]:
    """Add effects around the speaker where the speaker fills the frame (the only place they are drawn)."""
    busy = [(s.start, s.end) for s in layout if s.mode != "speaker"]
    kept = [g for g in around if not any(g.start < b and a < g.end for a, b in busy)]
    for i, g in enumerate(kept, 1):
        g.id = f"o{i}"
    return sorted(graphics + kept, key=lambda g: g.start)


def _behind(items: Any, duration: float, limit: int) -> list[Graphic]:
    """Big titles behind the speaker's head, as kinetic_text on the behind layer."""
    out: list[Graphic] = []
    for item in items if isinstance(items, list) else []:
        span = _span(item, duration)
        text = str(item.get("text") or "").strip() if isinstance(item, dict) else ""
        if span is None or not text:
            continue
        start, end = span
        out.append(Graphic(id="", type="kinetic_text", start=start, end=min(end, start + MAX_GRAPHIC_SECONDS),
                           props={"text": " ".join(text.split()[:3])[:24]}, layer="behind"))
    out.sort(key=lambda g: g.start)
    kept: list[Graphic] = []
    for g in out:
        if not kept or g.start >= kept[-1].end:
            kept.append(g)
    return kept[:limit]


def add_behind(graphics: list[Graphic], behind: list[Graphic], layout: list) -> list[Graphic]:
    """Add behind-the-speaker titles where the speaker fills the frame (the only place they are drawn
    behind), dropping front text graphics they overlap so the two don't fight."""
    busy = [(s.start, s.end) for s in layout if s.mode != "speaker"]
    overlaps = lambda a, b: a.start < b[1] and b[0] < a.end  # noqa: E731
    titles = [g for g in behind if not any(overlaps(g, s) for s in busy)]
    kept = [
        g for g in graphics
        if g.layer == "behind" or g.type not in ("kinetic_text", "stat_card")
        or not any(overlaps(g, (t.start, t.end)) for t in titles)
    ]
    for i, g in enumerate(titles, 1):
        g.id = f"b{i}"
    return sorted(kept + titles, key=lambda g: g.start)


def _backgrounds(items: Any, duration: float) -> list[BackgroundSpan]:
    out: list[BackgroundSpan] = []
    for item in items if isinstance(items, list) else []:
        span = _span(item, duration)
        if span is None or item.get("kind") not in BACKGROUNDS:
            continue
        out.append(BackgroundSpan(start=span[0], end=span[1], kind=item["kind"]))
    out.sort(key=lambda b: b.start)
    kept: list[BackgroundSpan] = []
    for b in out:
        if not kept or b.start >= kept[-1].end:
            kept.append(b)
    return kept


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
    valid_types = set(GENERATED_GRAPHIC_TYPES)
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
