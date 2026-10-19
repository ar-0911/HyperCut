"""The editor's assistant: a plain-language request becomes edits to the plan.

    assist(plan, "remove the subtitles from 5s to 9s", playhead=12.0) -> AssistResult

Claude sees a reel-time summary of the timeline and answers with a short list of operations; this module
validates them, converts reel time to source time (`hypercut.edit`) and applies them to a copy of the plan.
Illustrations it asks for are drawn by the same illustrator the analyze stage uses. One Claude call per
request, plus one per batch of new illustrations. CLI for manual runs:

    python -m hypercut.assistant plan.json "add an illustration of a rocket at 10s" [--out new.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hypercut import edit, llm
from hypercut import plan as plan_mod
from hypercut.analyze import cuts as cutting
from hypercut.analyze import motion, stage, visuals
from hypercut.analyze.analyze import MAX_AROUND_SECONDS, around_props, draw_around
from hypercut.analyze.transitions import LENGTH as CUT_LENGTH
from hypercut.plan import EditPlan

TEXT_TYPES = ("kinetic_text", "stat_card", "list_build", "lower_third")
MODES = ("speaker", "split", "visual")
# "gradient" is still read from older answers; it is drawn as the studio set like "color" (ADR 0613).
BACKGROUND_KINDS = ("original", "blur", "dim", "color", "gradient", "media")
CUT_KINDS = ("drop", "whip", "zoom", "push")
MAX_OPS = 20
MAX_ADD_SECONDS = 8.0

SYSTEM = (
    "You are the assistant inside a short-form video editor. You turn the user's request into edit "
    "operations on the timeline. Answer with JSON only."
)

PROMPT = """The reel is {duration:.1f} s long. The playhead is at {playhead:.1f} s. {selection}
Current look: speed {speed}, pause kept at cuts {keep_pause}s, cuts "{transition}", caption font "{font}".
All times below and in your answer are REEL seconds (what the viewer sees), as the reel is now.

Timeline items (key: type, reel start-end, details):
{items}

Layout spans (speaker = speaker fills the frame; split = visual panel on top, speaker and captions below;
visual = the visual fills the frame while the speaker keeps talking):
{layout}

Zooms:
{zooms}

Animated transitions:
{cuts}

Green-screen effects (speaker cut out of the frame): {depth}
Background stretches:
{backgrounds}

Imported files the user uploaded (use with add_media):
{assets}

Captions (reel time, words):
{captions}

User request: {instruction}

Operations you can use (times in reel seconds; keep the reel's own length in mind):
- {{"op": "delete", "keys": ["g1", "z0", "l2"]}}  remove graphics, zooms or layout spans by key
- {{"op": "remove_captions", "start": s, "end": e}}  hide the subtitles in that stretch
- {{"op": "cut", "start": s, "end": e}}  remove that stretch of video from the reel
- {{"op": "add_illustration", "start": s, "end": e, "title": "2-4 words", "brief": "what to draw: subject, \
composition, palette", "layout": "split" | "visual"}}  a new drawn illustration; split keeps the speaker \
and subtitles below it, visual makes it full screen
- {{"op": "add_text", "type": one of {text_types}, "start": s, "end": e, "props": {{...}}}}  props: \
kinetic_text {{"text"}}; stat_card {{"value","label"}}; list_build {{"title","items"}}; \
lower_third {{"title","subtitle"}}
- {{"op": "add_media", "asset": "<file name>", "start": s, "end": e, "layout": "split" | "visual"}}
- {{"op": "set_layout", "start": s, "end": e, "mode": "speaker" | "split" | "visual"}}
- {{"op": "add_zoom", "start": s, "end": e, "scale": 1.05-1.5}}
- {{"op": "move", "key": "g1", "start": s, "end": e}}
- {{"op": "edit", "key": "g1", "props": {{...}}}}  change a graphic's text or other props (merged in)
- {{"op": "caption_style", "changes": {{"font"|"color"|"highlight_color"|"size"|"position"|"uppercase"|\
"words_per_line"|"animation": value}}}}  fonts: {fonts}
- {{"op": "pacing", "speed": 0.7-1.3, "keep_pause": 0.08 (tight) | 0.15 (natural) | 0.3 (relaxed)}}  slow down or \
speed up the whole reel; keep_pause is how much pause stays around each cut (re-cuts the video)
- {{"op": "behind_text", "start": s, "end": e, "text": "1-3 words"}}  a big title BEHIND the speaker's head (green-screen look; turns the effects on and keeps the speaker full frame there)
- {{"op": "stage", "type": "card_stack" | "scene" | "chart", "start": s, "end": e, ...}}  a graphic of what is said, animated over the real footage beside the speaker (behind them only if the speaker is cut out), keeping the speaker full frame there. card_stack: "cards": [{{"title": "1-3 words", "brief": "what to draw"}}] (1-3 illustrated cards sliding in beside the speaker); scene: "title", "brief" (a drawn world replacing the room, speaker pulled back; only when a different background is asked for); chart: "headline", "kind": "line" | "bars", "values": [numbers], "labels": [..], "unit" (an animated chart, only for numbers said)
- {{"op": "around", "type": "orbit" | "fly_out" | "particles", "start": s, "end": e, "items": ["objects to draw, 1-3 words each"], "kind": "sparkles" | "bokeh" | "confetti" | "embers"}}  an effect happening AROUND the speaker, passing behind and in front of them (never over the face): orbit = drawn graphics circling the shoulders, fly_out = drawn graphics bursting from behind the head toward the camera, particles = drifting atmosphere (kind); turns the green-screen effects on and keeps the speaker full frame there
- {{"op": "layer", "key": "g1", "layer": "behind" | "front"}}  put a graphic behind the speaker or back in front
- {{"op": "background", "kind": "original" | "blur" | "dim" | "color" | "media", "start": s, "end": e, "color": "#RRGGBB", "asset": "<file name, for media>", "parallax": 0-1}}  change what is behind the speaker (turns the effects on); color = a studio set with a grid floor, its light tinted with "color" (never a flat colour); without start/end it applies to the whole reel; parallax drifts a replaced background for a 3D feel
- {{"op": "motion", "start": s, "end": e, "title": "1-4 words", "idea": "the one 3D object or moment to show"}}  a 2-3 s full-screen 3D motion graphic of what is said there (the speaker keeps talking)
- {{"op": "cut_transition", "at": s, "kind": "drop" | "whip" | "zoom" | "push" | "none"}}  an animated transition at a cut or shot change: drop = the old shot falls off screen, whip = a fast blurred pan, zoom = pushing through, push = slides up; "none" removes the one there. Use sparingly
- {{"op": "depth", "enabled": false}}  turn all green-screen effects off
- {{"op": "transitions", "style": "editorial" | "hard" | "smooth" | "zoom", "fade_out": seconds}}  editorial (J-cuts, \
punch-ins across jump cuts, a settle on new shots), hard cuts, short crossfades, or alternating punch-ins at cuts; fade to black at the end

A new visual (illustration, footage, big text, stat card, list) replaces any visual already in that stretch.
Use only what the request asks for; green-screen ops only when the user asks for something behind them,
a different background, or a depth/3D/green-screen look. "From X to Y" means start X, end Y. If a time is not given, use the
playhead. If the request is unclear or impossible, return no operations and say why in "message".
Return {{"message": "<one short sentence for the user>", "ops": [...]}}"""


@dataclass
class AssistResult:
    plan: EditPlan
    message: str
    changes: list[str] = field(default_factory=list)


def _fmt(span: tuple[float, float] | None) -> str:
    return "cut" if span is None else f"{span[0]:.1f}-{span[1]:.1f}"


def _detail(props: dict) -> str:
    keys = ("title", "text", "value", "label", "emoji", "subtitle", "items", "label", "kind", "idea")
    bits = [f"{k}={json.dumps(props[k], ensure_ascii=False)[:60]}" for k in keys if k in props]
    return ", ".join(dict.fromkeys(bits))


def summarize(plan: EditPlan, assets: list[dict]) -> dict[str, str]:
    items = [
        f"{g.id}: {g.type}{' (behind the speaker)' if g.layer == 'behind' else ''}, "
        f"{_fmt(edit.first_reel(plan, g.start, g.end))}, {_detail(g.props)}"
        for g in plan.graphics
    ]
    depth = plan.style.depth
    backgrounds = [f"bg{i}: {b.kind}, {_fmt(edit.first_reel(plan, b.start, b.end))}" for i, b in enumerate(plan.backgrounds)]
    layout = [f"l{i}: {s.mode}, {_fmt(edit.first_reel(plan, s.start, s.end))}" for i, s in enumerate(plan.layout)]
    zooms = [f"z{i}: x{z.scale}, {_fmt(edit.first_reel(plan, z.start, z.end))}" for i, z in enumerate(plan.zooms)]
    cuts = [f"{c.kind} at {hits[0]:.1f}" for c in plan.cuts if (hits := edit.to_reel(plan, c.at))]
    lines, line, line_t = [], [], None
    for w in plan.transcript.words:
        hits = edit.to_reel(plan, (w.start + w.end) / 2)
        if not hits:
            continue
        for t in hits:
            lines.append((t, w.text))
    lines.sort()
    captions = []
    for t, text in lines:
        if line_t is None or len(line) >= 8 or t - line_t > 3:
            if line:
                captions.append(f"{line_t:.1f} " + " ".join(line))
            line, line_t = [], t
        line.append(text)
    if line:
        captions.append(f"{line_t:.1f} " + " ".join(line))
    asset_lines = [f"{a['name']} ({a['kind']}, {a.get('label', '')})" for a in assets]
    return {
        "items": "\n".join(items) or "(none)",
        "layout": "\n".join(layout) or "(speaker throughout)",
        "zooms": "\n".join(zooms) or "(none)",
        "cuts": "\n".join(cuts) or "(none)",
        "depth": (f"on, speaker cut out, default background {depth.background}" if depth.cutout
                  else "on, real background kept") if depth.enabled else "off",
        "backgrounds": "\n".join(backgrounds) or "(none)",
        "assets": "\n".join(asset_lines) or "(none)",
        "captions": "\n".join(captions) or "(none)",
    }


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _reel_span(op: dict, duration: float, playhead: float, default_len: float = 3.0) -> tuple[float, float] | None:
    s = _num(op.get("start"))
    e = _num(op.get("end"))
    if s is None:
        s = playhead
    if e is None:
        e = s + default_len
    s, e = max(0.0, s), min(duration, e)
    return (s, e) if e > s else None


def apply_ops(plan: EditPlan, ops: list, playhead: float, assets: list[dict], draw=visuals.illustrate,
              audio_wav: str | None = None, draw_icons=visuals.draw_icons, design=None) -> tuple[EditPlan, list[str]]:
    """Validate and apply Claude's operations to a copy of the plan. Unknown or invalid ops are skipped."""
    plan = plan.model_copy(deep=True)
    duration = edit.reel_duration(plan)
    asset_by_name = {a["name"]: a for a in assets}
    changes: list[str] = []
    ops = [o for o in ops if isinstance(o, dict)][:MAX_OPS]

    # Keys refer to the plan as it was, so resolve them all before anything moves.
    by_key: dict[str, Any] = {g.id: g for g in plan.graphics}
    by_key.update({f"z{i}": z for i, z in enumerate(plan.zooms)})
    by_key.update({f"l{i}": s for i, s in enumerate(plan.layout)})
    by_key.update({f"bg{i}": b for i, b in enumerate(plan.backgrounds)})

    def span_of(op: dict, default_len: float = 3.0, cap: float | None = None) -> tuple[float, float] | None:
        r = _reel_span(op, duration, playhead, default_len)
        if r is None:
            return None
        if cap is not None:
            r = (r[0], min(r[1], r[0] + cap))
        return edit.source_span(plan, *r)

    pending_art: list[tuple[dict, tuple[float, float]]] = []
    moments: list[plan_mod.Graphic] = []
    cuts: list[tuple[float, float]] = []
    caption_cuts: list[tuple[float, float]] = []
    doomed: list[Any] = []
    gone = lambda item: any(item is d for d in doomed)  # identity: equal zooms are still different items
    recut = False

    for op in ops:
        kind = op.get("op")
        if kind == "delete":
            for key in op.get("keys") or []:
                if key in by_key and not gone(by_key[key]):
                    doomed.append(by_key[key])
                    changes.append(f"Removed {key}")
        elif kind == "remove_captions":
            r = _reel_span(op, duration, playhead)
            if r:
                caption_cuts.append(r)
        elif kind == "cut":
            r = _reel_span(op, duration, playhead)
            if r:
                cuts.append(r)
        elif kind == "add_illustration":
            span = span_of(op, 4.0, MAX_ADD_SECONDS)
            if span and str(op.get("brief") or op.get("title") or "").strip():
                pending_art.append((op, span))
        elif kind == "add_text" and op.get("type") in TEXT_TYPES:
            span = span_of(op, 2.5, MAX_ADD_SECONDS)
            if span:
                props = op.get("props") if isinstance(op.get("props"), dict) else {}
                g = edit.add_graphic(plan, op["type"], *span, props)
                changes.append(f"Added {op['type'].replace('_', ' ')} {g.id}")
                if op["type"] in edit.VISUAL_TYPES:
                    changes += [f"Replaced {x}" for x in edit.clear_visuals(plan, *span, keep=g.id)]
        elif kind == "add_media" and op.get("asset") in asset_by_name:
            a = asset_by_name[op["asset"]]
            span = span_of(op, min(4.0, float(a.get("duration") or 4.0)), MAX_ADD_SECONDS * 2)
            if span:
                props = {"src": a["name"], "kind": a["kind"], "fit": "cover", "label": a.get("label", "")}
                if a.get("duration"):
                    props["duration"] = a["duration"]
                g = edit.add_graphic(plan, "media", *span, props, prefix="m")
                edit.set_layout(plan, *span, "visual" if op.get("layout") == "visual" else "split")
                changes.append(f"Added {a.get('label') or a['name']} as {g.id}")
                changes += [f"Replaced {x}" for x in edit.clear_visuals(plan, *span, keep=g.id)]
        elif kind == "set_layout" and op.get("mode") in MODES:
            span = span_of(op)
            if span:
                edit.set_layout(plan, *span, op["mode"])
                changes.append(f"Layout {op['mode']} {_fmt(_reel_span(op, duration, playhead))}s")
        elif kind == "add_zoom":
            span = span_of(op, 1.5, 4.0)
            if span:
                edit.add_zoom(plan, *span, _num(op.get("scale")) or plan.style.camera.zoom_scale)
                changes.append("Added a zoom")
        elif kind == "move" and op.get("key") in by_key:
            span = span_of(op)
            target = by_key[op["key"]]
            if span and not gone(target):
                target.start, target.end = span
                changes.append(f"Moved {op['key']}")
        elif kind == "edit" and isinstance(by_key.get(op.get("key")), plan_mod.Graphic) and isinstance(op.get("props"), dict):
            g = by_key[op["key"]]
            g.props = {**g.props, **{k: v for k, v in op["props"].items() if k not in ("src", "layers", "defs", "viewBox")}}
            changes.append(f"Edited {g.id}")
        elif kind == "pacing":
            speed, pause = _num(op.get("speed")), _num(op.get("keep_pause"))
            if speed is not None:
                plan.style.pacing.speed = min(2.0, max(0.5, speed))
                changes.append(f"Speed {round(plan.style.pacing.speed * 100)}%")
            if pause is not None and abs(pause - plan.style.pacing.keep_pause) > 1e-6:
                plan.style.pacing.keep_pause = min(1.0, max(0.0, pause))
                recut = True
        elif kind == "behind_text" and str(op.get("text") or "").strip():
            span = span_of(op, 2.5, MAX_ADD_SECONDS)
            if span:
                text = " ".join(str(op["text"]).split()[:3])[:24]
                g = edit.add_graphic(plan, "kinetic_text", *span, {"text": text}, prefix="b")
                g.layer = "behind"
                edit.set_layout(plan, *span, "speaker")
                plan.style.depth.enabled = plan.style.depth.cutout = True  # asked for: behind needs the cut-out
                changes.append(f"Added {text!r} behind the speaker as {g.id}")
        elif kind == "stage" and op.get("type") in plan_mod.STAGE_GRAPHIC_TYPES:
            props = stage.stage_props(op["type"], op)
            span = span_of(op, 4.0, stage.MAX_SECONDS[op["type"]]) if props else None
            if span:
                g = edit.add_graphic(plan, op["type"], *span, props, prefix="s")
                edit.set_layout(plan, *span, "speaker")
                if op["type"] == "scene":  # a scene replaces the room, so it was a background ask (ADR 0614)
                    plan.style.depth.enabled = plan.style.depth.cutout = True
                where = "behind the speaker" if plan.style.depth.enabled and plan.style.depth.cutout else "beside the speaker"
                changes.append(f"Added {op['type'].replace('_', ' ')} {g.id} {where}")
        elif kind == "around" and op.get("type") in plan_mod.AROUND_GRAPHIC_TYPES:
            props = around_props(op["type"], op)
            span = span_of(op, 3.0, MAX_AROUND_SECONDS[op["type"]]) if props else None
            if span:
                g = edit.add_graphic(plan, op["type"], *span, props, prefix="o")
                edit.set_layout(plan, *span, "speaker")
                plan.style.depth.enabled = True
                changes.append(f"Added {op['type'].replace('_', ' ')} around the speaker as {g.id}")
        elif kind == "layer" and isinstance(by_key.get(op.get("key")), plan_mod.Graphic) and op.get("layer") in ("front", "behind"):
            g = by_key[op["key"]]
            g.layer = op["layer"]
            if g.layer == "behind":
                plan.style.depth.enabled = plan.style.depth.cutout = True
            changes.append(f"Moved {g.id} {'behind the speaker' if g.layer == 'behind' else 'to the front'}")
        elif kind == "background" and op.get("kind") in BACKGROUND_KINDS:
            src = None
            if op["kind"] == "media":
                a = asset_by_name.get(op.get("asset"))
                if a is None:
                    continue
                src = a["name"]
            color = op.get("color") if isinstance(op.get("color"), str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", op["color"]) else None
            parallax = min(1.0, max(0.0, _num(op.get("parallax")) or 0.0))
            plan.style.depth.enabled = plan.style.depth.cutout = True  # a background asked for by name
            if op.get("start") is None and op.get("end") is None and src is None and color is None and not parallax:
                plan.style.depth.background = op["kind"]
                plan.backgrounds = []
                changes.append(f"Background: {op['kind']} throughout")
            else:
                full = op.get("start") is None and op.get("end") is None
                span = (0.0, plan.source.duration) if full else span_of(op, 3.0)
                if span:
                    edit.set_background(plan, *span, plan_mod.BackgroundSpan(
                        start=span[0], end=span[1], kind=op["kind"], color=color, src=src, parallax=parallax))
                    changes.append(f"Background: {op['kind']}" + ("" if full else f" {_fmt(_reel_span(op, duration, playhead))}s"))
        elif kind == "motion" and str(op.get("idea") or op.get("title") or "").strip():
            span = span_of(op, 2.5, motion.MAX_SECONDS)
            if span:
                title = " ".join(str(op.get("title") or "").split()[:4])[:32]
                moments.append(plan_mod.Graphic(id="", type="motion", start=span[0], end=span[1],
                                                props={"title": title, "idea": str(op.get("idea") or title)[:400]}))
        elif kind == "cut_transition" and (op.get("kind") in CUT_KINDS or op.get("kind") == "none"):
            at = _num(op.get("at"))
            at = playhead if at is None else min(max(at, 0.0), duration)
            t = edit.to_source(plan, at)[0]
            plan.cuts = [c for c in plan.cuts if abs(c.at - t) > 1.0]
            if op["kind"] == "none":
                changes.append(f"Removed the transition at {at:.1f}s")
            else:
                plan.cuts = sorted(plan.cuts + [plan_mod.CutTransition(at=t, kind=op["kind"], length=CUT_LENGTH[op["kind"]])], key=lambda c: c.at)
                changes.append(f"Added a {op['kind']} transition at {at:.1f}s")
        elif kind == "depth" and op.get("enabled") is False:
            plan.style.depth.enabled = False
            changes.append("Turned green-screen effects off")
        elif kind == "transitions":
            t = plan.style.transitions
            if op.get("style") in ("editorial", "hard", "smooth", "zoom"):
                t.style = op["style"]
                changes.append(f"Cuts: {t.style}")
            if _num(op.get("fade_out")) is not None:
                t.fade_out = min(3.0, max(0.0, _num(op["fade_out"])))
                changes.append(f"Fade out {t.fade_out:.1f}s")
        elif kind == "caption_style" and isinstance(op.get("changes"), dict):
            data = plan.style.caption.model_dump()
            data.update({k: v for k, v in op["changes"].items() if k in data})
            try:
                plan.style.caption = plan_mod.CaptionStyle.model_validate(data)
                changes.append("Changed the caption style")
            except ValueError:
                pass

    if moments:
        motion.add_motion(plan, moments)
        motion.design_scenes(plan.graphics, plan.transcript, plan.style, design)
        changes += [f"Added motion graphic {g.id}" for g in moments]
    draw_around(plan.graphics, plan.style, draw_icons)
    stage.draw_stage(plan.graphics, plan.style, draw)
    if pending_art:
        drawn = draw([str(op.get("brief") or op.get("title")) for op, _ in pending_art])
        for (op, span), props in zip(pending_art, drawn):
            title = str(op.get("title") or "")[:40]
            if props is not None:
                g = edit.add_graphic(plan, "illustration", *span, {**props, "title": title, "brief": str(op.get("brief") or "")})
            else:  # drawing failed: keep the beat with its title as text
                g = edit.add_graphic(plan, "kinetic_text", *span, {"text": title or "…"})
            edit.set_layout(plan, *span, "visual" if op.get("layout") == "visual" else "split")
            changes.append(f"Added illustration {g.id}" + ("" if props is not None else " (as text; drawing failed)"))
            changes += [f"Replaced {x}" for x in edit.clear_visuals(plan, *span, keep=g.id)]

    plan.graphics = [g for g in plan.graphics if not gone(g)]
    plan.zooms = [z for z in plan.zooms if not gone(z)]
    plan.layout = [s for s in plan.layout if not gone(s)]
    plan.backgrounds = [b for b in plan.backgrounds if not gone(b)]

    if recut:
        # Rebuild the cuts for the new pause before reel-time cuts, which refer to the reel as it was;
        # the user's earlier clip deletions are rebuilt too, which the change message says.
        plan = cutting.recut(plan, audio_wav)
        changes.append(f"Re-cut with {plan.style.pacing.keep_pause:.2f}s pauses")

    # Reel times refer to the reel before this request: hide captions first, then cut from the end back.
    for a, b in caption_cuts:
        n = edit.remove_captions(plan, a, b)
        changes.append(f"Removed {n} caption words {a:.1f}-{b:.1f}s")
    for a, b in sorted(cuts, reverse=True):
        try:
            removed = edit.cut(plan, a, b)
            changes.append(f"Cut {removed:.1f}s at {a:.1f}s")
        except ValueError as e:
            changes.append(f"Skipped a cut: {e}")
    return EditPlan.model_validate(plan.model_dump()), changes


def assist(plan: EditPlan, instruction: str, playhead: float = 0.0, assets: list[dict] | None = None,
           selected: str | None = None, audio_wav: str | None = None) -> AssistResult:
    assets = assets or []
    selection = f"The user has {selected} selected." if selected else ""
    raw = llm.ask_json(
        PROMPT.format(
            duration=edit.reel_duration(plan), playhead=playhead, selection=selection,
            speed=plan.style.pacing.speed, keep_pause=plan.style.pacing.keep_pause,
            transition=plan.style.transitions.style, font=plan.style.caption.font,
            instruction=instruction.strip()[:2000], text_types=", ".join(TEXT_TYPES), fonts=", ".join(plan_mod.CAPTION_FONTS),
            **summarize(plan, assets),
        ),
        system=SYSTEM,
    )
    ops = raw.get("ops") if isinstance(raw.get("ops"), list) else []
    new_plan, changes = apply_ops(plan, ops, playhead, assets, audio_wav=audio_wav)
    message = str(raw.get("message") or "")[:300] or ("Done." if changes else "I couldn't make that change.")
    return AssistResult(new_plan, message, changes)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hypercut.assistant", description=__doc__.splitlines()[0])
    ap.add_argument("plan")
    ap.add_argument("instruction")
    ap.add_argument("--playhead", type=float, default=0.0, help="reel seconds")
    ap.add_argument("--out", help="write the edited plan here (default: print the changes only)")
    args = ap.parse_args(argv)
    result = assist(plan_mod.load(args.plan), args.instruction, args.playhead)
    print(result.message)
    for c in result.changes:
        print(" -", c)
    if args.out:
        plan_mod.save(result.plan, Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
