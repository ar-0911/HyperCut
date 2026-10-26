"""Motion graphics (ADR 0612): a few 2-3 second moments where the reel cuts away from the speaker to a
full-screen 3D scene of exactly what is being said, while the speaker keeps talking.

Two steps. The main analyze call picks the moments (`PROMPT`: when, a title, and the idea of what to show).
Then one more call designs every scene from the transcript (`design_scenes`): Claude writes a small JSON
description of the objects, their materials and how they move, which the renderer draws with three.js
(render/src/Motion.tsx). Nothing is picked from a fixed menu: a paint brand gets paint cans, a protein
shake gets a bottle, DNA gets a turning helix.
"""

from __future__ import annotations

import json
import math
from typing import Any

from hypercut import llm
from hypercut.plan import EditPlan, Graphic, Style, Transcript

MOTION_PER_MIN = 2  # at most; most reels need one or two
MIN_SECONDS, MAX_SECONDS = 1.8, 3.2
NO_MOTION_HEAD = 2.0  # never in the first seconds of the hook: the viewer must see who is talking

SHAPES = (
    "sphere", "box", "cylinder", "cone", "torus", "capsule", "lathe", "extrude", "text", "tube",
    "helix", "globe", "network", "bars", "stack", "ring", "grid", "group",
)
FINISHES = ("glossy", "metal", "matte", "glass", "emissive")
ANIMS = ("spin", "float", "pulse", "enter", "grow", "draw", "orbit", "fall")
ENTER_FROM = ("below", "above", "left", "right", "front", "scale")
AXES = ("x", "y", "z")
LOOKS = ("light", "dark")
MAX_OBJECTS = 24  # top level
MAX_DEPTH = 3  # nesting of children / pattern copies
MAX_POINTS = 48

PROMPT = """  "motion": [  // at most {max_motion} moments (usually 1-2 a minute, [] if nothing fits) where the reel cuts away from the speaker for 2-3 s to a full-screen 3D motion graphic of exactly what is being said: a concrete thing, place, process or number that can be shown, never an abstract feeling; never in the first 2 s; not overlapping each other
    {{"start": <s>, "end": <s>, "title": "<1-4 words, as said>", "idea": "<the one hero object or moment to show, specific to this video and these words, e.g. a paint can whose pour twists into a DNA helix>"}}
  ],
"""

DESIGN_SYSTEM = (
    "You are a senior 3D motion designer making premium product-shot style motion graphics for short "
    "vertical videos. You return JSON only."
)

DESIGN_PROMPT = """Design one 3D motion graphic for each moment below. Each plays full screen (portrait 1080x1920) \
for the given seconds while the speaker keeps talking, so it must show exactly what is being said there.

What the speaker says around each moment:
{moments}

Palette: accent {accent}, secondary {secondary}, panel {panel}. Use the names "accent", "secondary", "white" \
or hex colours that suit the subject (gold coins are gold, a heart is red). The scene stands in a studio with a \
grid floor: "look": "light" (pale grey, like a clean product shot; the default) or "dark" (near black, for \
night, space, tech or drama). Never a flat background of any colour.

THE BAR: it must look like a premium brand's product animation, not clip art.
- ONE hero subject filling 60-70% of the frame, specific to these words (a paint brand -> paint cans and a pour; \
a protein shake -> the shaker bottle; health -> a heart; growth -> bars and an arrow). Build it from real-looking \
parts with real proportions, not one primitive.
- One satisfying change: it assembles, pours, grows, stacks, draws on or turns; then it holds for at least \
1.2 s with slow, living motion (a slow spin or float).
- Spring-like entrances that settle (the renderer springs "enter"); stagger parts by 0.05-0.15 s.
- NEVER: emoji, flat icons, clip art, placeholder bars, text gradients, glow effects, bounce, typewriter text, \
lots of small floating objects, other brands' logos, busy backgrounds. No people or faces.

THE SPACE: y is up, z toward the camera, rotations in degrees. Build at any size around the origin with real \
proportions; the renderer scales and centres the whole scene under the title and stands it on the floor.

THE SCENE LANGUAGE: {{"look": "light"|"dark", "objects": [object, ...], "camera": {{"height": 0.6, "orbit": \
<deg/s, -15..15>, "push": <0..0.3 slow dolly in>}}}}. An object is {{"shape", "color", "finish", "position": [x,y,z], \
"rotation": [x,y,z], "scale", "anim": [..], "children": [objects, positioned relative to it]}} plus its shape's fields:
- sphere {{radius}}; box {{size: [w,h,d]}} (rounded edges); cylinder {{radius, height}}; cone {{radius, height}}; \
torus {{radius, tube}}; capsule {{radius, height}}
- lathe {{profile: [[radius, y], ...] bottom to top}}: anything round: bottles, cans, cups, jars, vases, bulbs, pills
- extrude {{path: "<SVG path d>", size: <width>, depth}}: flat outlines made solid (a leaf, a lightning bolt, a map pin)
- text {{text: "<1-12 chars>", size, depth}}: solid 3D letters or numbers (a figure that was said, "5X")
- tube {{points: [[x,y,z], ...], radius}}: smooth paths: arrows' shafts, routes, a pour, a heartbeat line, a straw
- helix {{count, height, radius, turns, colors: [a, b]}}: a DNA double helix
- globe {{radius, count: <number of route arcs>, colors: [routes, land]}}: a dotted Earth with routes
- network {{count, radius, colors}}: connected nodes with signals running along the links
- bars {{values: [...], height, spacing, colors}}: a 3D bar chart that grows
- stack {{of: object, count, spacing}}, ring {{of: object, count, radius}}, grid {{of: object, count, spacing}}: \
copies of one object (coins, blocks), each starting a little after the one before
- group {{children}}: just a parent to move parts together
finish: "glossy" (default, clear-coated), "metal", "matte", "glass", "emissive" (self-lit, for lights and lines).
anim (each optional, at/dur in seconds from the start): {{"type": "spin", "axis": "y", "speed": <rad/s>}}, \
{{"type": "float", "amount", "speed"}}, {{"type": "pulse", "amount", "bpm"}}, \
{{"type": "enter", "from": "below"|"above"|"left"|"right"|"front"|"scale", "at", "dur"}}, \
{{"type": "grow", "axis", "at", "dur"}}, {{"type": "draw", "at", "dur"}} (tubes draw on, text scales in), \
{{"type": "orbit", "radius", "speed", "axis"}}, {{"type": "fall", "at", "height"}} (drops in and settles).

Example, "it's in our DNA" for a paint company: {{"objects": [{{"shape": "helix", "count": 26, "height": 5.4, \
"radius": 0.85, "turns": 2.2, "colors": ["#C8102E", "#1F4E9C"], "rotation": [10, 0, -14], "anim": [{{"type": \
"spin", "axis": "y", "speed": 0.9}}]}}, {{"shape": "lathe", "profile": [[0, -0.5], [0.55, -0.5], [0.55, 0.45], \
[0.5, 0.5], [0, 0.5]], "color": "white", "finish": "metal", "position": [0.9, -2.2, 0.6], "scale": 0.8, \
"anim": [{{"type": "enter", "from": "below", "at": 0.1}}]}}], "camera": {{"orbit": 6, "push": 0.12}}, "look": "dark"}}

Return {{"scenes": [{{"id": "<moment id>", "scene": {{...}}}}, ...]}}, one per moment."""


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _clip(v: Any, lo: float, hi: float) -> float | None:
    x = _num(v)
    return None if x is None else min(hi, max(lo, x))


def _vec(v: Any, lim: float = 20.0) -> list[float] | None:
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        return None
    xs = [_clip(x, -lim, lim) for x in v]
    return None if any(x is None for x in xs) else xs  # type: ignore[return-value]


def _list(v: Any, n: int) -> list:
    return v[:n] if isinstance(v, list) else []


def _color(v: Any) -> str | None:
    if not isinstance(v, str):
        return None
    v = v.strip()
    if v in ("accent", "secondary", "panel", "white"):
        return v
    if v.startswith("#") and len(v) in (4, 7, 9) and all(c in "0123456789abcdefABCDEF" for c in v[1:]):
        return v
    return None


def _anim(a: Any) -> dict | None:
    if not isinstance(a, dict) or a.get("type") not in ANIMS:
        return None
    out: dict[str, Any] = {"type": a["type"]}
    for key, lo, hi in (("speed", -8, 8), ("amount", 0, 2), ("bpm", 20, 200), ("at", 0, 30), ("dur", 0.05, 5),
                        ("radius", 0, 8), ("height", 0, 20)):
        x = _clip(a.get(key), lo, hi)
        if x is not None:
            out[key] = x
    if a.get("axis") in AXES:
        out["axis"] = a["axis"]
    if a.get("from") in ENTER_FROM:
        out["from"] = a["from"]
    return out


def clean_object(o: Any, depth: int = 0) -> dict | None:
    """A scene object with only known fields and sane numbers, or None. Recursion is bounded."""
    if not isinstance(o, dict) or o.get("shape") not in SHAPES or depth > MAX_DEPTH:
        return None
    out: dict[str, Any] = {"shape": o["shape"]}
    if (c := _color(o.get("color"))) is not None:
        out["color"] = c
    if o.get("finish") in FINISHES:
        out["finish"] = o["finish"]
    for key in ("position", "rotation"):
        if (v := _vec(o.get(key), 400 if key == "rotation" else 20)) is not None:
            out[key] = v
    scale = o.get("scale")
    if (s := _clip(scale, 0.01, 20)) is not None:
        out["scale"] = s
    elif (v := _vec(scale)) is not None:
        out["scale"] = [min(20.0, max(0.01, x)) for x in v]
    size = o.get("size")
    if (s := _clip(size, 0.01, 12)) is not None:
        out["size"] = s
    elif (v := _vec(size, 12)) is not None:
        out["size"] = v
    for key, lo, hi in (("radius", 0.005, 6), ("height", 0.01, 14), ("tube", 0.005, 3), ("depth", 0.01, 3),
                        ("count", 1, 200), ("turns", 0.2, 8), ("spacing", 0.01, 6)):
        if (x := _clip(o.get(key), lo, hi)) is not None:
            out[key] = round(x) if key == "count" else x
    if isinstance(o.get("profile"), list):
        prof = [[_clip(p[0], 0, 6), _clip(p[1], -12, 12)] for p in o["profile"][:MAX_POINTS]
                if isinstance(p, (list, tuple)) and len(p) == 2]
        prof = [p for p in prof if None not in p]
        if len(prof) >= 2:
            out["profile"] = prof
    if isinstance(o.get("points"), list):
        pts = [v for v in (_vec(p) for p in o["points"][:MAX_POINTS]) if v is not None]
        if len(pts) >= 2:
            out["points"] = pts
    if isinstance(o.get("path"), str) and o["path"].strip():
        path = o["path"].strip()[:4000]
        if all(c in "MmLlHhVvCcSsQqTtAaZz0123456789.,-+eE \n\t" for c in path):
            out["path"] = path
    if isinstance(o.get("text"), str) and o["text"].strip():
        out["text"] = o["text"].strip()[:12]
    if isinstance(o.get("values"), list):
        vals = [x for x in (_clip(v, 0, 1e9) for v in o["values"][:10]) if x is not None]
        if vals:
            out["values"] = vals
    if isinstance(o.get("colors"), list):
        cols = [c for c in (_color(x) for x in o["colors"][:6]) if c]
        if cols:
            out["colors"] = cols
    anims = [a for a in (_anim(x) for x in _list(o.get("anim"), 6)) if a]
    if anims:
        out["anim"] = anims
    if (child := clean_object(o.get("of"), depth + 1)) is not None:
        out["of"] = child
    kids = [k for k in (clean_object(c, depth + 1) for c in _list(o.get("children"), MAX_OBJECTS)) if k]
    if kids:
        out["children"] = kids
    # Shapes that need a field to exist at all.
    needs = {"lathe": "profile", "extrude": "path", "text": "text", "tube": "points", "bars": "values",
             "stack": "of", "ring": "of", "grid": "of", "group": "children"}
    if o["shape"] in needs and needs[o["shape"]] not in out:
        return None
    return out


def clean_scene(scene: Any) -> dict | None:
    """A renderable scene from Claude's answer, or None if nothing in it can be drawn."""
    if not isinstance(scene, dict):
        return None
    objects = [x for x in (clean_object(o) for o in _list(scene.get("objects"), MAX_OBJECTS)) if x]
    if not objects:
        return None
    out: dict[str, Any] = {"objects": objects}
    cam = scene.get("camera") if isinstance(scene.get("camera"), dict) else {}
    camera = {k: x for k, lo, hi in (("distance", 3, 30), ("height", -6, 8), ("orbit", -40, 40), ("push", 0, 0.5))
              if (x := _clip(cam.get(k), lo, hi)) is not None}
    if camera:
        out["camera"] = camera
    if scene.get("look") in LOOKS:
        out["look"] = scene["look"]
    return out


def parse_motion(items: Any, duration: float, limit: int) -> list[Graphic]:
    """Valid, non-overlapping motion moments from the main analyze answer (scenes not designed yet)."""
    out: list[Graphic] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        start, end = _num(item.get("start")), _num(item.get("end"))
        idea = str(item.get("idea") or "").strip()
        if start is None or end is None or not idea or start < NO_MOTION_HEAD or start >= duration:
            continue
        end = min(end, duration, start + MAX_SECONDS)
        if end - start < MIN_SECONDS:
            continue
        title = " ".join(str(item.get("title") or "").split()[:4])[:32]
        out.append(Graphic(id="", type="motion", start=start, end=end, props={"title": title, "idea": idea[:400]}))
    out.sort(key=lambda g: g.start)
    kept: list[Graphic] = []
    for g in out:
        if not kept or g.start >= kept[-1].end:
            kept.append(g)
    return kept[:limit]


def add_motion(plan: EditPlan, moments: list[Graphic]) -> None:
    """Give each motion graphic the whole frame, in place: the layout is full-screen visual there, and
    other visuals, stage graphics and effects around the speaker at the same time make way."""
    from hypercut import edit

    taken = {g.id for g in plan.graphics}
    n = 0
    for g in moments:
        n += 1
        while f"m{n}" in taken:
            n += 1
        g.id = f"m{n}"
        edit.clear_visuals(plan, g.start, g.end, keep="")
        edit.set_layout(plan, g.start, g.end, "visual")
    clash = lambda x: x.type in ("card_stack", "scene", "chart", "orbit", "fly_out", "particles") and any(  # noqa: E731
        x.start < m.end and m.start < x.end for m in moments)
    plan.graphics = sorted([x for x in plan.graphics if not clash(x)] + moments, key=lambda x: x.start)


CLIP_LOOK = ("premium product-shot 3D animation, one hero subject, soft studio light, a clean {look} studio with a "
             "subtle grid floor, accents {accent} and {secondary}")


def clip_request(g: Graphic, style: Style) -> dict:
    """What to ask a video model for, for one motion moment (ADR 0016): its idea, in the reel's colours."""
    gs = style.graphics
    look = (g.props.get("scene") or {}).get("look", "light")
    return {
        "kind": "video",
        "prompt": f"{g.props.get('idea', '')} ({g.props.get('title', '')})".strip(),
        "look": CLIP_LOOK.format(look="pale grey" if look == "light" else "near-black", accent=gs.accent_color,
                                 secondary=gs.secondary_color or gs.accent_color),
    }


def ask_for_clips(plan: EditPlan, moments: list[Graphic]) -> None:
    """Have each motion moment fetched as a generated clip (by `hypercut.generate`), keeping its 3D scene."""
    for g in moments:
        if g.type == "motion" and not isinstance(g.props.get("generate"), dict):
            g.props = {**g.props, "generate": clip_request(g, plan.style)}


def _context(transcript: Transcript, g: Graphic, pad: float = 4.0) -> str:
    words = [w.text for w in transcript.words if g.start - pad <= w.start <= g.end + pad]
    said = " ".join(w.text for w in transcript.words if g.start <= w.start < g.end)
    return f'- id "{g.id}", {g.end - g.start:.1f} s, title "{g.props.get("title", "")}", idea: {g.props.get("idea", "")}\n' \
           f'  said during it: "{said}"\n  around it: "{" ".join(words)}"'


def design_scenes(graphics: list[Graphic], transcript: Transcript, style: Style, ask=None) -> bool:
    """Design the 3D scene of every motion graphic that has none yet (props.scene), in place, in one Claude
    call. Moments whose scene can't be made are left without one (the renderer then shows the title on the
    studio backdrop). True if any scene was added."""
    todo = [g for g in graphics if g.type == "motion" and not g.props.get("scene")]
    if not todo:
        return False
    gs = style.graphics
    prompt = DESIGN_PROMPT.format(
        moments="\n".join(_context(transcript, g) for g in todo),
        accent=gs.accent_color, secondary=gs.secondary_color or gs.accent_color, panel=gs.panel_color,
    )
    try:
        raw = (ask or llm.ask_json)(prompt, system=DESIGN_SYSTEM)
    except Exception:  # noqa: BLE001 - a missing scene must never fail the edit
        return False
    by_id = {}
    for item in raw.get("scenes", []) if isinstance(raw, dict) else []:
        if isinstance(item, dict) and (scene := clean_scene(item.get("scene"))):
            by_id[str(item.get("id"))] = scene
    changed = False
    for i, g in enumerate(todo):
        scene = by_id.get(g.id) or (by_id.get(str(i)) if len(by_id) == len(todo) else None)
        if scene:
            g.props = {**g.props, "scene": scene}
            changed = True
    return changed


def scene_json(g: Graphic) -> str:
    """The scene of a motion graphic, compact (for logs and tests)."""
    return json.dumps(g.props.get("scene"), separators=(",", ":"))
