"""Visual direction: split the kept speech into beats, pick a layout per beat, and draw original
illustrations for them. See docs/decisions/0402-layout-mix-and-illustrations.md.

Two kinds of Claude call:
1. One "director" call (with web search, for reference only) that picks each beat's layout mode and
   writes an art brief specific to what is said.
2. Parallel "illustrator" calls that turn briefs into SVG. Code sanitizes the SVG and splits it into
   layers the renderer reveals one by one.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from hypercut import llm
from hypercut.plan import Graphic, LayoutSpan, Segment, Style, Transcript

log = logging.getLogger(__name__)

MIN_BEAT = 2.2  # seconds of kept speech before a beat may end at a sentence break
MAX_BEAT = 4.5  # seconds of kept speech before a beat ends at the next word
MAX_VISUAL_SHARE = 0.3  # of output time in "visual" (speaker hidden) mode
ILLUSTRATIONS_PER_CALL = 3
PARALLEL_CALLS = 4
MAX_LAYERS = 12
VIEWBOX = "0 0 1000 800"
MODES = ("speaker", "split", "visual")
PANEL_KINDS = ("illustration", "kinetic_text", "stat_card", "list_build")
# Visuals fetched by `hypercut.generate` (ADR 0016), offered only when this machine can fetch them:
# footage = real stock footage or photos, picture = a generated still.
SOURCE_KINDS = {"footage": "stock", "picture": "image"}
# Analyze graphics that would fight a visual for the panel; overlays like lower thirds stay.
PANEL_TYPES = {"kinetic_text", "stat_card", "list_build", "illustration"}

# How a still moves while it is on screen (render: MediaFill), alternated so consecutive pictures differ.
MOVES = ("push_in", "pan_left", "pull_out", "pan_right", "rise")

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
ALLOWED_TAGS = {
    "svg", "g", "defs", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text",
    "tspan", "linearGradient", "radialGradient", "stop", "clipPath", "mask", "use", "title", "desc",
}


@dataclass
class Beat:
    start: float  # source seconds; beats tile the kept range with no gaps
    end: float
    text: str
    kept: float  # seconds of it that are actually played


# --- beats --------------------------------------------------------------------------------------


def make_beats(transcript: Transcript, segments: list[Segment], duration: float) -> list[Beat]:
    """Group the played words into beats of a few seconds, breaking at sentence ends when possible."""
    kept = _merge([(s.start, s.end) for s in segments] or [(0.0, duration)])
    words = [w for w in transcript.words if any(a <= (w.start + w.end) / 2 < b for a, b in kept)]
    if not words:
        return []
    groups: list[list] = [[]]
    for w in words:
        cur = groups[-1]
        cur.append(w)
        played = _played(kept, cur[0].start, w.end)
        if played >= MAX_BEAT or (played >= MIN_BEAT and w.text.rstrip()[-1:] in ".?!,;:"):
            groups.append([])
    if not groups[-1]:
        groups.pop()
    if len(groups) > 1 and _played(kept, groups[-1][0].start, groups[-1][-1].end) < MIN_BEAT / 2:
        groups[-2] += groups.pop()  # don't end on a sliver

    beats = []
    for i, g in enumerate(groups):
        start = kept[0][0] if i == 0 else g[0].start
        end = kept[-1][1] if i == len(groups) - 1 else groups[i + 1][0].start
        if end <= start:
            continue
        beats.append(Beat(round(start, 3), round(end, 3), " ".join(w.text for w in g), _played(kept, start, end)))
    # Tile: each beat runs until the next one starts.
    for a, b in zip(beats, beats[1:]):
        a.end = b.start
    return [b for b in beats if b.end > b.start]


def _merge(ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for a, b in sorted(ranges):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _played(kept: list[tuple[float, float]], start: float, end: float) -> float:
    return sum(max(0.0, min(b, end) - max(a, start)) for a, b in kept)


# --- direction ----------------------------------------------------------------------------------

DIRECTOR_SYSTEM = (
    "You are the motion designer of a vertical short (Reels/TikTok) in the style of top creator "
    "explainers: the frame keeps changing between the speaker alone, a split screen with an animated "
    "illustration above the speaker, and brief full-screen illustrations while they keep talking. "
    "Answer with JSON only."
)

DIRECTOR_PROMPT = """The video's beats, in source order (hook first if one is marked):
{beats}

Context: {context}

For every beat choose:
- "mode": "speaker" (speaker alone; for personal moments, names, emotion, the first beat of the hook \
unless it is a strong visual), "split" (speaker below, visual above; the workhorse) or "visual" \
(visual fills the frame, at most {max_visual} beats, never two in a row, never the first beat).
- For split/visual beats a "visual": either
  {{"kind": "illustration", "title": "<0-4 words or empty>", "brief": "<art direction>"}} or
  {{"kind": "kinetic_text", "text": "<2-4 punchy words>"}} or {{"kind": "stat_card", "value": "...", \
"label": "..."}} or {{"kind": "list_build", "items": [..up to 4..]}}.
  Prefer illustrations (about 70%). Each brief must be SPECIFIC to what is said in that beat: the \
concrete objects, people, places, products and actions mentioned, and what they look like. If a brand, \
product, company or place is named, search the web to learn what it really looks like (colors, \
packaging shape, logo colors, uniforms, setting) and put those details in the brief, but describe an \
original drawing; never ask to copy a logo or photo. Briefs are for a flat vector illustrator: name the \
2-6 elements, their arrangement, and a palette of 3-5 hex colors that suits the speaker's setting and \
the accent color {accent}. Keep a consistent visual language across beats.
{sources}Use mode "speaker" for at least a quarter of the beats. Vary the rhythm: avoid three beats in a row with \
the same mode.

Return {{{look}"beats": [{{"i": <beat index>, "mode": "...", "visual": {{...}} or null}}, ...]}}"""

SOURCES_PROMPT = """Besides drawings, this editor can also show:
{options}
Choose per beat what serves it best: a drawing for diagrams, processes, lists and anything abstract; \
{prefer}. Every one of these still needs a "title" (0-4 words) and a "brief" (what the ideal shot shows; it is \
drawn instead if nothing fits).
"""
FOOTAGE_OPTION = """- {"kind": "footage", "query": "<2-5 plain words to search a stock library, e.g. 'aerial city night \
traffic'>", "media": "video" | "image", "title": "...", "brief": "..."}: real stock footage (B-roll) of real \
places, objects and actions mentioned (a factory line, a city, a lab, a kitchen, a crowd). Never a named \
person, brand or logo."""
PICTURE_OPTION = """- {"kind": "picture", "prompt": "<a generation prompt: the subject, what it is doing, setting, \
camera angle, light; specific to the words>", "title": "...", "brief": "..."}: a generated photo-real or 3D \
picture, for concepts and scenes no stock shot shows (the inside of a cell, a product idea, a historic scene). \
No text, logos, real people or faces in it."""
LOOK_FIELD = '"look": "<one line every generated picture shares so they match, e.g. editorial 3D render, soft \
studio light, coral and blue accents>", '

ILLUSTRATOR_SYSTEM = (
    "You are a flat-vector motion illustrator. You write clean, hand-crafted SVG by hand. "
    "Answer with JSON only."
)

ILLUSTRATOR_PROMPT = """Draw one SVG illustration per brief.

Rules for every SVG:
- Root: <svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}">. {canvas}
- Put gradients/clipPaths in one <defs>. Then 4-10 top-level <g> groups, in the order they should \
animate in: background shape first, then the main subject, then supporting details, then small accents \
(sparkles, arrows, motion lines). Each top-level group is one animation layer.
- Flat modern editorial style: bold simple shapes, rounded corners, thick dark outlines (#111111, \
6-12px) on key shapes, soft shadow shapes, the palette from the brief. Draw people as friendly \
simplified characters (no detailed faces). Make it read instantly on a phone.
- Text only if the brief asks for a word or two; then large, bold, font-family Montserrat, Arial.
- Not allowed: <script>, <style>, <image>, <foreignObject>, animation elements, filters, external \
links, event attributes, copies of real logos.
- Keep each SVG under 7000 characters.

Briefs:
{briefs}

Return {{"svgs": [{{"i": <brief index>, "svg": "<svg ...>...</svg>"}}, ...]}}"""


def sources_prompt(sources: set[str]) -> str:
    """The extra visual kinds the director may pick, for the asset kinds this machine can fetch."""
    options, prefer = [], []
    if "stock" in sources:
        options.append(FOOTAGE_OPTION)
        prefer.append("footage when a real thing, place or action is named (about a third of the visuals)")
    if "image" in sources:
        options.append(PICTURE_OPTION)
        prefer.append("a picture when a concrete scene or object can't be filmed")
    return SOURCES_PROMPT.format(options="\n".join(options), prefer="; ".join(prefer)) if options else ""


def direct(
    beats: list[Beat],
    style: Style,
    hook_span: tuple[float, float] | None = None,
    context: str = "",
    sources: set[str] | None = None,
) -> list[dict]:
    """One director call: mode + visual per beat, cleaned up and constrained in code. `sources`: the asset kinds
    (`hypercut.generate.available()`) the director may also use. With "image", the first pick carries the reel's
    shared "look" line."""
    lines = []
    for i, b in enumerate(beats):
        hook = " [HOOK, plays first]" if hook_span and b.start < hook_span[1] and hook_span[0] < b.end else ""
        lines.append(f'{i} ({b.kept:.1f}s){hook}: "{b.text}"')
    max_visual = max(1, int(len(beats) * MAX_VISUAL_SHARE))
    raw = llm.ask_json(
        DIRECTOR_PROMPT.format(
            beats="\n".join(lines),
            context=context or "a talking-head video",
            max_visual=max_visual,
            accent=style.graphics.accent_color,
            sources=sources_prompt(sources or set()),
            look=LOOK_FIELD if "image" in (sources or set()) else "",
        ),
        system=DIRECTOR_SYSTEM,
        timeout=600,
        web_search=True,
    )
    picks: dict[int, dict] = {}
    for item in raw.get("beats") or []:
        if isinstance(item, dict) and isinstance(item.get("i"), int) and 0 <= item["i"] < len(beats):
            picks[item["i"]] = item
    out = []
    for i in range(len(beats)):
        item = picks.get(i, {})
        mode = item.get("mode") if item.get("mode") in MODES else "speaker"
        visual = _visual(item.get("visual"), sources or set()) if mode != "speaker" else None
        if visual is None:
            mode = "speaker"
        out.append({"mode": mode, "visual": visual})
    look = " ".join(str(raw.get("look") or "").split())[:200]
    if out and look:
        out[0]["look"] = look
    return _constrain(out, beats)


def _visual(v: Any, sources: set[str] = frozenset()) -> dict | None:
    if not isinstance(v, dict):
        return None
    kind = v.get("kind")
    if kind in SOURCE_KINDS and SOURCE_KINDS[kind] in sources:
        words = str(v.get("query" if kind == "footage" else "prompt") or "").strip()
        brief = str(v.get("brief") or "").strip()[:1500]
        if not words:
            return None
        out = {"kind": kind, "title": str(v.get("title") or "")[:40], "brief": brief or words}
        if kind == "footage":
            out.update(query=" ".join(words.split()[:8])[:80], media=v.get("media") if v.get("media") in ("video", "image") else "video")
        else:
            out["prompt"] = words[:1000]
        return out
    if kind not in PANEL_KINDS:
        return None
    if kind == "illustration":
        brief = str(v.get("brief") or "").strip()
        return {"kind": kind, "brief": brief[:1500], "title": str(v.get("title") or "")[:40]} if brief else None
    if kind == "kinetic_text":
        text = str(v.get("text") or "").strip()
        return {"kind": kind, "text": text[:40]} if text else None
    if kind == "stat_card":
        return {"kind": kind, "value": str(v.get("value") or "")[:16], "label": str(v.get("label") or "")[:40]}
    items = [str(x)[:30] for x in v.get("items") or [] if str(x).strip()][:4]
    return {"kind": kind, "items": items} if items else None


def _constrain(picks: list[dict], beats: list[Beat]) -> list[dict]:
    """No visual-only first beat, no two in a row, and visual-only time under the cap."""
    total = sum(b.kept for b in beats) or 1.0
    visual_time = 0.0
    for i, p in enumerate(picks):
        if p["mode"] != "visual":
            continue
        if i == 0 or picks[i - 1]["mode"] == "visual" or (visual_time + beats[i].kept) / total > MAX_VISUAL_SHARE:
            p["mode"] = "split"
        else:
            visual_time += beats[i].kept
    return picks


# --- illustration -------------------------------------------------------------------------------


LANDSCAPE = "Landscape-ish 1000x800 canvas."
PORTRAIT = "Tall 1080x1920 canvas filled edge to edge (a full scene, it is a background); keep the middle third \
and the bottom half calm, a person stands there."
PORTRAIT_VIEWBOX = "0 0 1080 1920"


def illustrate(briefs: list[str], viewbox: str = VIEWBOX, canvas: str = LANDSCAPE) -> list[dict | None]:
    """Draw every brief (in parallel batches). Each result is illustration props or None on failure."""
    batches = [list(range(i, min(i + ILLUSTRATIONS_PER_CALL, len(briefs)))) for i in range(0, len(briefs), ILLUSTRATIONS_PER_CALL)]
    results: list[dict | None] = [None] * len(briefs)

    def draw(idx: list[int]) -> None:
        text = "\n".join(f"{j}: {briefs[k]}" for j, k in enumerate(idx))
        try:
            raw = llm.ask_json(ILLUSTRATOR_PROMPT.format(viewbox=viewbox, canvas=canvas, briefs=text), system=ILLUSTRATOR_SYSTEM, timeout=900)
        except llm.LLMError as e:
            log.warning("illustration batch failed: %s", e)
            return
        for item in raw.get("svgs") or []:
            if not isinstance(item, dict) or not isinstance(item.get("i"), int) or not 0 <= item["i"] < len(idx):
                continue
            try:
                results[idx[item["i"]]] = svg_layers(str(item.get("svg") or ""))
            except ValueError as e:
                log.warning("illustration %d rejected: %s", idx[item["i"]], e)

    with ThreadPoolExecutor(max_workers=PARALLEL_CALLS) as pool:
        list(pool.map(draw, batches))
    return results


ICON_VIEWBOX = "0 0 400 400"
ICONS_PER_CALL = 6

ICON_PROMPT = """Draw one small sticker graphic per item. They float around a person in a short vertical video \
(orbiting their shoulders or flying out from behind their head), so each must read instantly at 150 px.

Rules for every SVG:
- Root: <svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}">. One object, centred, filling about \
80% of the square, on a transparent background (no backdrop shape, no frame).
- Bold flat-vector sticker style: simple chunky shapes, thick dark outlines (#111111, 10-14px, round \
joins), flat fills (no gradients, no <defs>), one lighter highlight shape, a slight 3/4 view for depth. \
Palette: {palette}, plus white, #111111 and one complementary colour. No text unless the item is a number \
or symbol (then large and bold, font-family Montserrat, Arial).
- Not allowed: <script>, <style>, <image>, <foreignObject>, <defs>, gradients, filters, animation \
elements, external links, event attributes, copies of real logos.
- Keep each SVG under 2500 characters.

Items:
{items}

Return {{"svgs": [{{"i": <item index>, "svg": "<svg ...>...</svg>"}}, ...]}}"""


def draw_icons(items: list[str], palette: str = "#FFD60A") -> list[dict | None]:
    """Draw each item (e.g. "rocket", "stack of coins") as a small sticker SVG for the effects around the
    speaker (ADR 0610). Each result is {"viewBox", "body"} or None when drawing failed."""
    batches = [list(range(i, min(i + ICONS_PER_CALL, len(items)))) for i in range(0, len(items), ICONS_PER_CALL)]
    results: list[dict | None] = [None] * len(items)

    def draw(idx: list[int]) -> None:
        text = "\n".join(f"{j}: {items[k]}" for j, k in enumerate(idx))
        try:
            raw = llm.ask_json(ICON_PROMPT.format(viewbox=ICON_VIEWBOX, palette=palette, items=text), system=ILLUSTRATOR_SYSTEM, timeout=600)
        except llm.LLMError as e:
            log.warning("icon batch failed: %s", e)
            return
        for item in raw.get("svgs") or []:
            if not isinstance(item, dict) or not isinstance(item.get("i"), int) or not 0 <= item["i"] < len(idx):
                continue
            try:
                layers = svg_layers(str(item.get("svg") or ""))
            except ValueError as e:
                log.warning("icon %d rejected: %s", idx[item["i"]], e)
                continue
            # Several icons share the frame, so ids in <defs> could clash: icons are drawn without them.
            results[idx[item["i"]]] = {"viewBox": layers["viewBox"], "body": "".join(layers["layers"])}

    with ThreadPoolExecutor(max_workers=PARALLEL_CALLS) as pool:
        list(pool.map(draw, batches))
    return results


def svg_layers(svg: str) -> dict:
    """Sanitize an SVG and split it into {"viewBox", "defs", "layers"} for the renderer.

    Only plain drawing elements survive: no scripts, styles, foreign content, external references or
    event handlers. Raises ValueError when nothing drawable is left.
    """
    try:
        root = ET.fromstring(svg.strip())
    except ET.ParseError as e:
        raise ValueError(f"not valid SVG: {e}") from e
    if _local(root.tag) != "svg":
        raise ValueError("root is not <svg>")
    _clean(root)
    view_box = root.get("viewBox") or VIEWBOX
    if not re.fullmatch(r"\s*-?[\d.]+(\s+|,)-?[\d.]+(\s+|,)[\d.]+(\s+|,)[\d.]+\s*", view_box):
        view_box = VIEWBOX
    defs = "".join(_inner(d) for d in root if _local(d.tag) == "defs")
    layers = [_xml(el) for el in root if _local(el.tag) not in ("defs", "title", "desc")]
    if not layers:
        raise ValueError("no drawable layers")
    if len(layers) > MAX_LAYERS:  # fold the tail into the last layer so reveal stays snappy
        layers = layers[: MAX_LAYERS - 1] + ["<g>" + "".join(layers[MAX_LAYERS - 1 :]) + "</g>"]
    return {"viewBox": view_box.strip(), "defs": defs, "layers": layers}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _clean(el: ET.Element) -> None:
    for child in list(el):
        if _local(child.tag) not in ALLOWED_TAGS:
            el.remove(child)
        else:
            _clean(child)
    for name in list(el.attrib):
        local, value = _local(name).lower(), el.attrib[name]
        urls = re.findall(r"url\(([^)]*)\)", value)
        if (
            local.startswith("on")
            or (local == "href" and not value.startswith("#"))
            or "javascript:" in value.lower()
            or any(not u.strip(" '\"").startswith("#") for u in urls)
        ):
            del el.attrib[name]


def _xml(el: ET.Element) -> str:
    # Children serialize with a default-namespace declaration; strip it, the renderer's <svg> has it.
    return re.sub(r'\sxmlns(:\w+)?="[^"]*"', "", ET.tostring(el, encoding="unicode"))


def _inner(el: ET.Element) -> str:
    return "".join(_xml(c) for c in el)


# --- assemble -----------------------------------------------------------------------------------


def plan_visuals(
    transcript: Transcript,
    segments: list[Segment],
    duration: float,
    style: Style,
    hook_span: tuple[float, float] | None = None,
    context: str = "",
    sources: set[str] | None = None,
) -> tuple[list[LayoutSpan], list[Graphic]]:
    """Layout spans and visual graphics for the whole video. Empty lists when there is no speech.

    Footage and pictures (only offered for `sources` this machine can fetch) come back as `media` graphics with a
    `generate` request and no file yet; `hypercut.generate` fetches them."""
    beats = make_beats(transcript, segments, duration)
    if not beats:
        return [], []
    picks = direct(beats, style, hook_span, context, sources)
    look = picks[0].get("look", "") if picks else ""

    need = [i for i, p in enumerate(picks) if p["visual"] and p["visual"]["kind"] == "illustration"]
    drawn = illustrate([picks[i]["visual"]["brief"] for i in need]) if need else []
    art = dict(zip(need, drawn))

    layout: list[LayoutSpan] = []
    graphics: list[Graphic] = []
    for i, (beat, pick) in enumerate(zip(beats, picks)):
        v = pick["visual"]
        graphic = None
        if v and v["kind"] == "illustration":
            props = art.get(i)
            if props is not None:
                graphic = ("illustration", {**props, "title": v["title"], "brief": v["brief"]})
            elif v["title"]:  # drawing failed: keep the beat visual with its title as text
                graphic = ("kinetic_text", {"text": v["title"]})
        elif v and v["kind"] in SOURCE_KINDS:
            req = {"kind": SOURCE_KINDS[v["kind"]]}
            req.update({"query": v["query"], "media": v["media"]} if v["kind"] == "footage" else {"prompt": v["prompt"], "look": look})
            graphic = ("media", {"generate": req, "title": v["title"], "brief": v["brief"], "label": v["title"],
                                 "fit": "cover", "kind": v.get("media", "image"), "move": MOVES[len(graphics) % len(MOVES)]})
        elif v:
            graphic = (v["kind"], {k: val for k, val in v.items() if k != "kind"})
        mode = pick["mode"] if graphic else "speaker"
        if graphic:
            graphics.append(Graphic(id=f"v{len(graphics) + 1}", type=graphic[0], start=beat.start, end=beat.end, props=graphic[1]))
        if layout and layout[-1].mode == mode and abs(layout[-1].end - beat.start) < 1e-6:
            layout[-1].end = beat.end
        else:
            layout.append(LayoutSpan(start=beat.start, end=beat.end, mode=mode))
    return layout, graphics


def merge_graphics(existing: list[Graphic], visuals: list[Graphic], layout: list[LayoutSpan]) -> list[Graphic]:
    """Keep overlay graphics, drop panel-type ones that would collide with a split/visual beat."""
    busy = [(s.start, s.end) for s in layout if s.mode != "speaker"]
    keep = [
        g for g in existing
        if g.type not in PANEL_TYPES or not any(g.start < b and a < g.end for a, b in busy)
    ]
    return sorted(keep + visuals, key=lambda g: g.start)
