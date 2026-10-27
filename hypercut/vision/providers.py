"""Vision-language providers for the visual index (ADR 0024): one interface, swappable models.

    get("none" | "ollama" | "claude").describe(frames, times) -> [ {description, scene_type, visible_text,
                                                                   objects, people, confidence} | None, ... ]

- none: describes nothing; the index keeps its local signals (shots, on-screen text, brightness). Default.
- ollama: a vision model served by Ollama on this machine (`HYPERCUT_OLLAMA_URL`, default
  http://localhost:11434; `HYPERCUT_VLM_MODEL`, default qwen2.5vl:7b). Frames never leave the machine.
- claude: frames go to Claude through `hypercut.llm.ask_json(images=...)`, on the user's subscription or API
  key. Frames leave the machine, so this is only used when the user turns it on.

A provider that fails returns None for the frames it could not describe; the index is still written.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.request
from pathlib import Path

from hypercut import llm

log = logging.getLogger(__name__)
BATCH = 8
TYPES = ("talking_head", "interview", "screen", "product", "b_roll", "text", "unknown")

PROMPT = """These are {n} frames from a video, in order, each at a source time:
{frames}
For each frame say what is visible, for a video editor deciding which shot to show while someone talks.
Return {{"frames": [{{"frame": <number>, "description": "<one short sentence: who or what is on screen, doing what>", \
"scene_type": one of {types}, "visible_text": ["<words readable on screen>"], "objects": ["<up to 6 notable things: \
product, phone, laptop, dashboard, whiteboard...>"], "people": <count>, "confidence": <0..1>}}]}}
scene_type: talking_head = one person talking to camera; interview = two or more people talking; screen = a screen \
recording, app, website or slide; product = an object being shown or used; b_roll = other footage (a place, an \
activity); text = a title card. JSON only."""


def _clean(d: dict) -> dict | None:
    if not isinstance(d, dict):
        return None
    kind = d.get("scene_type") if d.get("scene_type") in TYPES else "unknown"
    try:
        conf = min(1.0, max(0.0, float(d.get("confidence", 0.6))))
    except (TypeError, ValueError):
        conf = 0.6
    people = d.get("people")
    return {
        "description": str(d.get("description") or "")[:200],
        "scene_type": kind,
        "visible_text": [str(t)[:80] for t in (d.get("visible_text") or []) if str(t).strip()][:20],
        "objects": [str(o)[:40] for o in (d.get("objects") or []) if str(o).strip()][:8],
        "people": int(people) if isinstance(people, (int, float)) and people >= 0 else None,
        "confidence": conf,
    }


def merge(obs, d: dict) -> None:
    """Fold a model's description into an observation, keeping local OCR text the model missed."""
    obs.description = d["description"]
    obs.scene_type = d["scene_type"]
    obs.objects = d["objects"]
    obs.people = d["people"]
    obs.confidence = d["confidence"]
    obs.visible_text = list(dict.fromkeys(d["visible_text"] + obs.visible_text))[:20]


class Provider:
    name = "none"

    def describe(self, frames: list[Path], times: list[float]) -> list[dict | None]:
        return [None] * len(frames)


class Claude(Provider):
    name = "claude"

    def describe(self, frames: list[Path], times: list[float]) -> list[dict | None]:
        out: list[dict | None] = [None] * len(frames)
        for start in range(0, len(frames), BATCH):
            batch = frames[start:start + BATCH]
            listing = "\n".join(f"{i}: {times[start + i]:.1f} s" for i in range(len(batch)))
            try:
                raw = llm.ask_json(PROMPT.format(n=len(batch), frames=listing, types=list(TYPES)), images=batch)
            except llm.LLMError as e:
                log.warning("describing frames failed: %s", e)
                continue
            for item in raw.get("frames") or []:
                i = item.get("frame") if isinstance(item, dict) else None
                if isinstance(i, int) and 0 <= i < len(batch):
                    out[start + i] = _clean(item)
        return out


class Ollama(Provider):
    name = "ollama"

    def __init__(self, url: str | None = None, model: str | None = None, opener=urllib.request.urlopen):
        self.url = (url or os.environ.get("HYPERCUT_OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.environ.get("HYPERCUT_VLM_MODEL", "qwen2.5vl:7b")
        self.opener = opener

    def describe(self, frames: list[Path], times: list[float]) -> list[dict | None]:
        out: list[dict | None] = []
        for frame, t in zip(frames, times):
            body = {
                "model": self.model, "stream": False, "format": "json",
                "prompt": PROMPT.format(n=1, frames=f"0: {t:.1f} s", types=list(TYPES)),
                "images": [base64.b64encode(frame.read_bytes()).decode()],
            }
            req = urllib.request.Request(f"{self.url}/api/generate", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            try:
                with self.opener(req, timeout=180) as res:
                    answer = llm.extract_json(json.loads(res.read())["response"])
                items = answer.get("frames") or [answer]
                out.append(_clean(items[0]) if items else None)
            except Exception as e:  # a local model that isn't running must not stop the pipeline
                log.warning("Ollama could not describe %s: %s", frame.name, e)
                out.append(None)
        return out


def get(name: str | None) -> Provider:
    name = (name or os.environ.get("HYPERCUT_VISION") or "none").lower()
    return {"claude": Claude, "ollama": Ollama}.get(name, Provider)()
