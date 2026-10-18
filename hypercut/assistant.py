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
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hypercut import edit, llm
from hypercut import plan as plan_mod
from hypercut.analyze import visuals
from hypercut.plan import EditPlan

TEXT_TYPES = ("kinetic_text", "stat_card", "list_build", "lower_third", "emoji_burst")
MODES = ("speaker", "split", "visual")
MAX_OPS = 20
MAX_ADD_SECONDS = 8.0

SYSTEM = (
    "You are the assistant inside a short-form video editor. You turn the user's request into edit "
    "operations on the timeline. Answer with JSON only."
)

PROMPT = """The reel is {duration:.1f} s long. The playhead is at {playhead:.1f} s. {selection}
All times below and in your answer are REEL seconds (what the viewer sees), as the reel is now.

Timeline items (key: type, reel start-end, details):
{items}

Layout spans (speaker = speaker fills the frame; split = visual panel on top, speaker and captions below;
visual = the visual fills the frame while the speaker keeps talking):
{layout}

Zooms:
{zooms}

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
lower_third {{"title","subtitle"}}; emoji_burst {{"emoji"}}
- {{"op": "add_media", "asset": "<file name>", "start": s, "end": e, "layout": "split" | "visual"}}
- {{"op": "set_layout", "start": s, "end": e, "mode": "speaker" | "split" | "visual"}}
- {{"op": "add_zoom", "start": s, "end": e, "scale": 1.05-1.5}}
- {{"op": "move", "key": "g1", "start": s, "end": e}}
- {{"op": "edit", "key": "g1", "props": {{...}}}}  change a graphic's text or other props (merged in)
- {{"op": "caption_style", "changes": {{"color"|"highlight_color"|"size"|"position"|"uppercase"|\
"words_per_line"|"animation": value}}}}

A new visual (illustration, footage, big text, stat card, list) replaces any visual already in that stretch.
Use only what the request asks for. "From X to Y" means start X, end Y. If a time is not given, use the
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
    keys = ("title", "text", "value", "label", "emoji", "subtitle", "items", "label", "kind")
    bits = [f"{k}={json.dumps(props[k], ensure_ascii=False)[:60]}" for k in keys if k in props]
    return ", ".join(dict.fromkeys(bits))


def summarize(plan: EditPlan, assets: list[dict]) -> dict[str, str]:
    items = [
        f"{g.id}: {g.type}, {_fmt(edit.first_reel(plan, g.start, g.end))}, {_detail(g.props)}"
        for g in plan.graphics
    ]
    layout = [f"l{i}: {s.mode}, {_fmt(edit.first_reel(plan, s.start, s.end))}" for i, s in enumerate(plan.layout)]
    zooms = [f"z{i}: x{z.scale}, {_fmt(edit.first_reel(plan, z.start, z.end))}" for i, z in enumerate(plan.zooms)]
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


def apply_ops(plan: EditPlan, ops: list, playhead: float, assets: list[dict], draw=visuals.illustrate) -> tuple[EditPlan, list[str]]:
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

    def span_of(op: dict, default_len: float = 3.0, cap: float | None = None) -> tuple[float, float] | None:
        r = _reel_span(op, duration, playhead, default_len)
        if r is None:
            return None
        if cap is not None:
            r = (r[0], min(r[1], r[0] + cap))
        return edit.source_span(plan, *r)

    pending_art: list[tuple[dict, tuple[float, float]]] = []
    cuts: list[tuple[float, float]] = []
    caption_cuts: list[tuple[float, float]] = []
    doomed: list[Any] = []
    gone = lambda item: any(item is d for d in doomed)  # identity: equal zooms are still different items

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
        elif kind == "caption_style" and isinstance(op.get("changes"), dict):
            data = plan.style.caption.model_dump()
            data.update({k: v for k, v in op["changes"].items() if k in data})
            try:
                plan.style.caption = plan_mod.CaptionStyle.model_validate(data)
                changes.append("Changed the caption style")
            except ValueError:
                pass

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
           selected: str | None = None) -> AssistResult:
    assets = assets or []
    selection = f"The user has {selected} selected." if selected else ""
    raw = llm.ask_json(
        PROMPT.format(
            duration=edit.reel_duration(plan), playhead=playhead, selection=selection,
            instruction=instruction.strip()[:2000], text_types=", ".join(TEXT_TYPES), **summarize(plan, assets),
        ),
        system=SYSTEM,
    )
    ops = raw.get("ops") if isinstance(raw.get("ops"), list) else []
    new_plan, changes = apply_ops(plan, ops, playhead, assets)
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
