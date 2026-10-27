"""Editing modes: policies for the editing decisions, applied to the same timeline engine (ADR 0025).

    apply(style, "podcast", prompt_changes) -> Style      # the mode's pacing, camera, graphics and cuts
    guidance("product_demo") -> str                       # what the planner should favour in this mode

A style says how the reel LOOKS (font, colours). A mode says how it is EDITED: what makes a hook, how tight the
pauses are, how often the picture changes, how many graphics and of which kind, how footage meets footage. Every mode
runs through the same stages and produces the same plan, so a user can start as a podcast clip and later say "make it
more cinematic" (or switch mode in the editor) without losing the edit: switching re-applies the mode's settings and
re-cuts the pauses, and the hook, graphics and manual edits stay.

The mode is stored in `plan.style.mode`. The style prompt still wins over a mode for anything it asks for.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hypercut.plan import Style

DEFAULT_MODE = "talking_head"


@dataclass(frozen=True)
class Mode:
    name: str
    label: str
    description: str
    guidance: str  # added to the analyze prompt
    # Style fields the mode sets (nested dicts, merged over the preset), e.g. {"pacing": {"keep_pause": 0.12}}.
    style: dict = field(default_factory=dict)


MODES: dict[str, Mode] = {m.name: m for m in (
    Mode(
        "talking_head", "Talking head",
        "One person talking to camera: a strong hook, tight pauses, captions and graphics where they help.",
        "",
    ),
    Mode(
        "podcast", "Podcast clip",
        "A moment from a conversation: the strongest standalone answer, dead air removed, frequent but sensible "
        "visual changes, emphasis on the speaker.",
        """Editing mode: PODCAST CLIP. The reel is a self-contained moment from a conversation.
- Hook: the boldest standalone claim or answer; if the answer needs its question to make sense, start at the question.
- Keep one thread of thought; leave out tangents, cross-talk and "yeah, yeah" back-channel.
- Change the picture often but sensibly: punch-ins on emphasised words, a new zoom every few seconds.
- Graphics: big text for the key phrase and stat cards for numbers said; no decorative illustrations.
- When more than one person talks, the person speaking is on screen.""",
        {"pacing": {"keep_pause": 0.12, "max_silence": 0.3, "remove_fillers": True},
         "camera": {"zoom_frequency": "high"},
         "graphics": {"density": "balanced"},
         "caption": {"animation": "karaoke", "words_per_line": 3},
         "transitions": {"style": "editorial"}},
    ),
    Mode(
        "product_demo", "Product demo",
        "Explaining a product: clear structure, the screen or product left visible, feature callouts, clean "
        "professional type.",
        """Editing mode: PRODUCT DEMO. The reel explains what a product does.
- Hook: the problem it solves or its most impressive result, in one line.
- Structure: problem, what it does, how (the feature shown), result, call to action. Keep every step that
  explains; cut repetition.
- Leave screen recordings and product shots clearly visible: never cover them with drawings or big text.
- Graphics: lower thirds and short labels naming each feature as it is shown; list_build for steps; numbers as
  stat cards. Nothing playful.
- Zooms only to point at a detail being explained.""",
        {"pacing": {"keep_pause": 0.15, "max_silence": 0.5},
         "camera": {"zoom_frequency": "low"},
         "graphics": {"density": "balanced", "theme": "clean"},
         "caption": {"font": "Inter", "weight": 700, "uppercase": False, "words_per_line": 4, "animation": "karaoke",
                     "stroke_width": 0, "box": "#000000B3"},
         "transitions": {"style": "hard"}},
    ),
    Mode(
        "vlog", "Vlog / story",
        "A story: narrative flow with a beginning, middle and end, visual variety, room for emotional beats.",
        """Editing mode: VLOG / STORYTELLING. The reel tells a story.
- Hook: the most intriguing moment of the story, a question or tension the rest resolves.
- Keep the narrative order and the setup a payoff needs; end on the resolution or the feeling, not mid-thought.
- Let emotional beats breathe: keep the pause after a punchline or a reveal.
- Visual variety: alternate footage, drawn scenes and full-screen motion moments; avoid text-heavy graphics.
- Fewer, longer zooms that follow the mood.""",
        {"pacing": {"keep_pause": 0.25, "max_silence": 0.6},
         "camera": {"zoom_frequency": "low", "zoom_scale": 1.1},
         "graphics": {"density": "minimal", "theme": "cinematic"},
         "transitions": {"style": "smooth", "length": 0.25, "fade_out": 1.2}},
    ),
)}


def get(name: str | None) -> Mode:
    return MODES.get(name or DEFAULT_MODE, MODES[DEFAULT_MODE])


def _merge(base: dict, changes: dict) -> dict:
    out = dict(base)
    for k, v in changes.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def changed(style: Style, base: Style) -> dict:
    """The nested fields of `style` that differ from `base` (what a style prompt asked for)."""
    def walk(a: dict, b: dict) -> dict:
        out = {}
        for k, v in a.items():
            if isinstance(v, dict) and isinstance(b.get(k), dict):
                sub = walk(v, b[k])
                if sub:
                    out[k] = sub
            elif v != b.get(k):
                out[k] = v
        return out
    return walk(style.model_dump(), base.model_dump())


def asked_for(style: Style) -> dict:
    """What a style prompt, recipe or editor change set beyond its preset and current mode: kept when a mode
    is applied over it, so switching mode replaces only the old mode's settings."""
    return changed(style, apply(_preset(style), style.mode, keep={}))


def _preset(style: Style) -> Style:
    from hypercut.style import PRESETS

    base = PRESETS.get(style.name)
    return base if base is not None else Style(name=style.name)


def apply(style: Style, mode: str, keep: dict | None = None) -> Style:
    """`style` with the mode's editing settings, then `keep` on top.

    Without `keep`, the result is the style's preset, then the mode, then whatever the user set beyond the
    preset and the old mode (`asked_for`), so switching mode never leaves the old mode's settings behind.
    """
    m = get(mode)
    if keep is None:
        keep, style = asked_for(style), _preset(style)
    keep = {k: v for k, v in keep.items() if k != "mode"}
    merged = _merge(_merge(style.model_dump(), m.style), keep)
    merged["mode"] = m.name
    return Style.model_validate(merged)


def guidance(mode: str | None) -> str:
    text = get(mode).guidance
    return f"\n\n{text}" if text else ""


def listing() -> list[dict]:
    return [{"name": m.name, "label": m.label, "description": m.description} for m in MODES.values()]
