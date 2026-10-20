"""Recipes: named styles saved from the editor and reused on new uploads (ADR 0018).

One JSON file, `media/recipes.json`, local like everything else: {"recipes": [{"name", "style", "note", "created"}]}.
A recipe is a whole `Style` (captions, colours, graphics mix, pacing, cuts, camera, effects), so a new video made
with it skips the style prompt and looks like the edit it was saved from.
"""

from __future__ import annotations

import json
import threading
import time

from api import jobs
from hypercut.plan import Style

MAX_RECIPES = 50
_lock = threading.Lock()


def _path():
    return jobs.media_root() / "recipes.json"


def _read() -> list[dict]:
    try:
        return json.loads(_path().read_text()).get("recipes", [])
    except (FileNotFoundError, ValueError):
        return []


def _write(recipes: list[dict]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"recipes": recipes}, indent=2))
    tmp.replace(path)


def all_recipes() -> list[dict]:
    return _read()


def get(name: str) -> Style | None:
    for r in _read():
        if r["name"] == name:
            return Style.model_validate(r["style"])
    return None


def save(name: str, style: Style, note: str = "") -> dict:
    """Add a recipe, or replace the one with the same name."""
    name = " ".join(name.split())[:60]
    if not name:
        raise ValueError("a recipe needs a name")
    record = {"name": name, "style": style.model_dump(mode="json"), "note": note[:200], "created": time.time()}
    with _lock:
        recipes = [r for r in _read() if r["name"] != name]
        if len(recipes) >= MAX_RECIPES:
            raise ValueError(f"up to {MAX_RECIPES} recipes; delete one first")
        _write(recipes + [record])
    return record


def delete(name: str) -> bool:
    with _lock:
        recipes = _read()
        kept = [r for r in recipes if r["name"] != name]
        _write(kept)
    return len(kept) != len(recipes)
