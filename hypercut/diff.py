"""What changed between two plans, in words a creator understands (ADR 0021).

    explain(before, after) -> ["Removed 2.4 s at 0:12.3", "Added an illustration “Rocket launch” at 0:10.0-0:13.0", ...]

Used for every version in the history, whoever made the change (the editor, the assistant, the render
review), so the history always says what happened. Times are reel times of the plan they refer to: removed
things are placed on the reel before the change, added things on the reel after it. Pure functions.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from hypercut import edit
from hypercut.plan import EditPlan, Graphic

EPS = 1e-3
NAMES = {
    "kinetic_text": "big text", "stat_card": "stat card", "emoji_burst": "emoji burst", "list_build": "list",
    "lower_third": "lower third", "progress_bar": "progress bar", "illustration": "illustration",
    "media": "imported clip", "orbit": "orbit effect", "fly_out": "fly-out effect", "particles": "particles",
    "card_stack": "card stack", "scene": "drawn scene", "chart": "chart", "motion": "motion graphic",
}


def article(noun: str) -> str:
    return f"{'an' if noun[:1] in 'aeiou' else 'a'} {noun}"


def clock(t: float) -> str:
    m, s = divmod(max(t, 0.0), 60)
    return f"{int(m)}:{s:04.1f}"


def _reel_span(plan: EditPlan, start: float, end: float) -> str:
    r = edit.first_reel(plan, start, end)
    return f"{clock(r[0])}-{clock(r[1])}" if r else "(cut from the reel)"


def title_of(g: Graphic) -> str:
    p = g.props or {}
    for key in ("title", "text", "headline", "label", "value", "idea"):
        if isinstance(p.get(key), str) and p[key].strip():
            text = p[key].strip()
            return f" “{text[:40]}{'…' if len(text) > 40 else ''}”"
    return ""


def _kept(plan: EditPlan) -> list[tuple[float, float]]:
    segs = plan.segments or []
    spans = sorted((s.start, s.end) for s in segs) if segs else [(0.0, plan.source.duration)]
    merged: list[tuple[float, float]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1] + EPS:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def _minus(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Source spans in a and not in b."""
    out = []
    for s, e in a:
        cursor = s
        for bs, be in b:
            if be <= cursor or bs >= e:
                continue
            if bs > cursor:
                out.append((cursor, bs))
            cursor = max(cursor, be)
        if cursor < e:
            out.append((cursor, e))
    return [(s, e) for s, e in out if e - s > 0.04]


def _segments(before: EditPlan, after: EditPlan) -> list[str]:
    out = []
    for s, e in _minus(_kept(before), _kept(after)):
        out.append(f"Removed {e - s:.1f} s at {_reel_span(before, s, e).split('-')[0]}")
    for s, e in _minus(_kept(after), _kept(before)):
        out.append(f"Put back {e - s:.1f} s at {_reel_span(after, s, e).split('-')[0]}")
    hook_b = [(s.start, s.end) for s in before.segments if s.reason == "hook"]
    hook_a = [(s.start, s.end) for s in after.segments if s.reason == "hook"]
    if hook_b != hook_a:
        if not hook_a:
            out.append("Removed the cold-open hook")
        else:
            words = [w.text for w in after.transcript.words if hook_a[0][0] - EPS <= w.start < hook_a[-1][1]]
            text = " ".join(words[:10]) + ("…" if len(words) > 10 else "")
            out.append(f"Opens with “{text}”" if text else "Changed the opening hook")
    elif not out and [(s.start, s.end) for s in before.segments] != [(s.start, s.end) for s in after.segments]:
        out.append("Reordered the clips")
    return out


def _graphics(before: EditPlan, after: EditPlan) -> list[str]:
    out = []
    old = {g.id: g for g in before.graphics}
    new = {g.id: g for g in after.graphics}
    for gid, g in old.items():
        if gid not in new:
            out.append(f"Removed the {NAMES.get(g.type, g.type)}{title_of(g)} at {_reel_span(before, g.start, g.end)}")
    for gid, g in new.items():
        if gid not in old:
            out.append(f"Added {article(NAMES.get(g.type, g.type))}{title_of(g)} at {_reel_span(after, g.start, g.end)}")
            continue
        o = old[gid]
        name = f"the {NAMES.get(g.type, g.type)}{title_of(g)}"
        if abs(o.start - g.start) > EPS or abs(o.end - g.end) > EPS:
            out.append(f"Moved {name} to {_reel_span(after, g.start, g.end)}")
        if o.props != g.props:
            keys = sorted(k for k in set(o.props) | set(g.props) if o.props.get(k) != g.props.get(k))
            shown = [k for k in keys if k not in ("layers", "defs", "viewBox", "art", "scene")] or ["drawing"]
            out.append(f"Changed {name}: {', '.join(shown[:4])}")
        if o.anchor != g.anchor:
            out.append(f"Placed {name} at the {g.anchor}")
        if o.layer != g.layer:
            out.append(f"Put {name} {'behind the speaker' if g.layer == 'behind' else 'in front'}")
    return out


def _spans(before: EditPlan, after: EditPlan, field: str, noun: str, describe) -> list[str]:
    a = [describe(x) for x in getattr(before, field)]
    b = [describe(x) for x in getattr(after, field)]
    out = []
    for item in getattr(before, field):
        if describe(item) not in b:
            out.append(f"Removed {noun} at {_reel_span(before, item.start, item.end)}")
    for item in getattr(after, field):
        if describe(item) not in a:
            extra = f" ({item.mode})" if field == "layout" else f" ({item.kind})" if field == "backgrounds" else ""
            out.append(f"Added {noun}{extra} at {_reel_span(after, item.start, item.end)}")
    return out


def _transcript(before: EditPlan, after: EditPlan) -> list[str]:
    a, b = before.transcript.words, after.transcript.words
    if [(w.start, w.end, w.text) for w in a] == [(w.start, w.end, w.text) for w in b]:
        return []
    out = []
    by_time = {(round(w.start, 3), round(w.end, 3)): w.text for w in a}
    edited = [(by_time[k], w.text) for w in b if (k := (round(w.start, 3), round(w.end, 3))) in by_time and by_time[k] != w.text]
    for old, new in edited[:5]:
        out.append(f"Caption “{old}” now reads “{new}”")
    if len(edited) > 5:
        out.append(f"Edited {len(edited) - 5} more caption words")
    if len(b) < len(a):
        out.append(f"Hid {len(a) - len(b)} caption words")
    elif len(b) > len(a):
        out.append(f"Added {len(b) - len(a)} caption words")
    return out


def _fields(a: Any, b: Any, path: str) -> list[str]:
    """Changed leaf settings of two pydantic models, as 'Caption font: Montserrat → Inter'."""
    out = []
    for key in type(a).model_fields:
        va, vb = getattr(a, key), getattr(b, key)
        if va == vb:
            continue
        label = f"{path} {key.replace('_', ' ')}".strip()
        if isinstance(va, BaseModel) and isinstance(vb, BaseModel):
            out += _fields(va, vb, label)
        else:
            out.append(f"{label[0].upper()}{label[1:]}: {va} → {vb}")
    return out


def explain(before: EditPlan, after: EditPlan) -> list[str]:
    """Every meaningful difference from `before` to `after`, most important first."""
    out = _segments(before, after)
    out += _graphics(before, after)
    out += _spans(before, after, "zooms", "a zoom", lambda z: (z.start, z.end, z.scale, z.ease))
    out += _spans(before, after, "layout", "a layout change", lambda s: (s.start, s.end, s.mode))
    out += _spans(before, after, "backgrounds", "a background", lambda s: (s.start, s.end, s.kind, s.color, s.src))
    ca, cb = {c.at: c.kind for c in before.cuts}, {c.at: c.kind for c in after.cuts}
    for at, kind in cb.items():
        if ca.get(at) != kind:
            r = edit.to_reel(after, at)
            out.append(f"Added a {kind} transition at {clock(r[0]) if r else clock(at)}")
    for at in ca.keys() - cb.keys():
        r = edit.to_reel(before, at)
        out.append(f"Removed the transition at {clock(r[0]) if r else clock(at)}")
    out += _transcript(before, after)
    if before.hook.chosen != after.hook.chosen and after.hook.candidates:
        out.append(f"Picked hook {after.hook.chosen + 1}: “{after.hook.candidates[after.hook.chosen].text[:60]}”")
    if before.hook.strategy != after.hook.strategy:
        out.append("Hook plays first as a cold open" if after.hook.strategy == "cold_open" else "Reel starts at the hook")
    out += _fields(before.style, after.style, "")
    if before.reframe != after.reframe:
        out.append("Changed the framing")
    if before.output != after.output:
        out.append(f"Output: {after.output.width}x{after.output.height} at {after.output.fps:g} fps")
    db, da = before.output_duration(), after.output_duration()
    if abs(db - da) > 0.05 and out:
        out.append(f"Reel is now {da:.1f} s ({da - db:+.1f} s)")
    return out
