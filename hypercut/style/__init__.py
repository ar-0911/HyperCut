"""hypercut.style: named presets and prompt-to-style via Claude.

Entry point: `style_from_prompt(prompt) -> Style`. See docs/decisions/0301-*.
"""

from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError

from hypercut import llm
from hypercut.plan import Style
from hypercut.style.presets import DEFAULT_PRESET, DESCRIPTIONS, PRESETS

__all__ = ["DEFAULT_PRESET", "asks_for_depth", "PRESETS", "get_preset", "list_presets", "style_from_prompt"]

log = logging.getLogger(__name__)

ATTEMPTS = 2  # one try plus one retry

SYSTEM = "You configure the look of a short-form video editor. Reply with one JSON object and nothing else."


def list_presets() -> list[str]:
    return list(PRESETS)


def get_preset(name: str) -> Style:
    """A fresh copy of a preset, so callers can't mutate the shared one."""
    try:
        return PRESETS[name].model_copy(deep=True)
    except KeyError:
        raise KeyError(f"unknown style preset {name!r}; choose from {', '.join(PRESETS)}") from None


def style_from_prompt(prompt: str) -> Style:
    """Turn a free-text style prompt into a validated `Style`.

    Claude picks the closest preset and returns only the fields to change. An invalid answer is
    retried once; after that the preset (or bold_creator if none was chosen) is returned.
    """
    if not prompt or not prompt.strip():
        return get_preset(DEFAULT_PRESET)

    fallback = DEFAULT_PRESET
    request = _build_prompt(prompt.strip())
    for attempt in range(1, ATTEMPTS + 1):
        try:
            answer = llm.ask_json(request, system=SYSTEM)
            preset = answer.get("preset")
            if preset not in PRESETS:
                raise ValueError(f"unknown preset {preset!r}")
            fallback = preset
            style = _merge(get_preset(preset), answer.get("changes") or {})
            if style.depth.enabled and not asks_for_depth(prompt):
                style.depth.enabled = False  # the user never asked for it (ADR 0901)
            return style
        except (llm.LLMError, ValidationError, ValueError, TypeError, AttributeError) as e:
            log.warning("style attempt %d/%d failed: %s", attempt, ATTEMPTS, e)
    return get_preset(fallback)


# Words a request for green-screen effects can't do without. A second check on Claude's answer, because
# these effects must never switch on by themselves (ADR 0901).
DEPTH_WORDS = re.compile(
    r"background|backdrop|behind|green ?screen|chroma|cut ?out|matte|3 ?d\b|depth|parallax|bokeh|blur|"
    r"pop(?:s|ping)? out|spotlight|segment|around (?:me|the speaker|him|her|them)|immersive|orbit|"
    r"particles?|sparkles?|confetti|in front of (?:me|the speaker)|remove (?:the|my) (?:room|wall)|replace (?:the|my) (?:room|wall)",
    re.IGNORECASE,
)


def asks_for_depth(prompt: str) -> bool:
    """Whether a style prompt could be asking for green-screen effects."""
    return bool(DEPTH_WORDS.search(prompt or ""))


def _merge(base: Style, changes: dict) -> Style:
    if not isinstance(changes, dict):
        raise ValueError("`changes` must be an object")
    merged = _deep_merge(base.model_dump(), changes)
    merged["name"] = base.name  # the preset name, whatever Claude wrote
    return Style.model_validate(merged)  # extra="forbid" rejects invented fields


def _deep_merge(base: dict, changes: dict) -> dict:
    out = dict(base)
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _build_prompt(user_prompt: str) -> str:
    presets = "\n".join(f"- {n}: {DESCRIPTIONS[n]}" for n in PRESETS)
    defaults = json.dumps({n: s.model_dump(exclude={"name"}) for n, s in PRESETS.items()}, indent=1)
    schema = json.dumps(Style.model_json_schema(), indent=1)
    return f"""Pick the preset closest to the user's request, then list only the fields that must differ from it.

Presets:
{presets}

Each preset's full values:
{defaults}

Style JSON schema (use only these fields and allowed values; colors are #RRGGBB):
{schema}

User request: {user_prompt}

Green-screen effects (`depth`) stay off unless the request explicitly asks for them: text or graphics
behind the speaker, things happening around or in front of the speaker (an immersive look), removing,
replacing, blurring or dimming the background, a green-screen, cut-out or 3D depth look. Then set depth.enabled true and pick depth.background (original keeps the real room).

Answer exactly: {{"preset": "<preset name>", "changes": {{...partial style, same nesting as the schema, omit `name`...}}}}
Use an empty "changes" object if the preset already fits."""
