"""Opt-in usage counts, kept on this computer (ADR 0030).

    on = enabled(root)                       # off until the person turns it on
    record(root, "render_done", seconds=212)  # dropped when off; only listed fields survive
    summary(root)                            # what the settings page shows

Nothing is sent anywhere. With telemetry on, HyperCut appends small events to `telemetry.jsonl` in the media
folder: which steps people use, how long they take, what fails, whether a suggestion was kept. Never footage,
frames, audio, transcripts, prompts, file names or paths: every event has a fixed list of fields, numbers or
values from a fixed set, and anything else is dropped. The person can read the file, download it to share with
whoever makes their copy of HyperCut, or delete it.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

FILE = "telemetry.jsonl"
SETTINGS = "settings.json"
MAX_BYTES = 2_000_000  # the log is trimmed to its newer half past this

NUMBER, FLAG = "number", "flag"
MODES = {"talking_head", "podcast", "product_demo", "vlog"}
STAGES = {"ingest", "transcribe", "style", "look", "analyze", "matte", "generate", "render", "unknown"}
KINDS = {"shorter", "hook", "tighter"}

# Every event and its fields: NUMBER, FLAG, or the set of values allowed.
EVENTS: dict[str, dict] = {
    "job_created": {"mode": MODES, "kit": FLAG, "pictures": FLAG, "recipe": FLAG, "style_prompt": FLAG},
    "job_done": {"seconds": NUMBER, "reel_seconds": NUMBER},
    "job_failed": {"stage": STAGES},
    "render_done": {"seconds": NUMBER},
    "render_failed": {},
    "qa": {"ok": FLAG, "failures": NUMBER},
    "suggestion": {"kind": KINDS, "outcome": {"shown", "tried", "kept", "put_back", "skipped", "none"}},
    "view": {"simple": FLAG},
    "edit_saved": {"kind": {"edit", "assistant", "review", "restore", "kit", "render"}},
    "assistant_asked": {"accepted": FLAG},
    "project_saved": {"footage": FLAG},
    "project_opened": {},
    "kit_applied": {},
    "share": {"how": {"share_sheet", "download", "copy_caption"}},
    "download": {},
}
# What the web app may send itself; the rest the server records.
CLIENT_EVENTS = {"suggestion", "view", "share", "download", "assistant_asked"}

_lock = threading.Lock()


def _settings(root: Path) -> dict:
    try:
        return json.loads((root / SETTINGS).read_text())
    except (OSError, ValueError):
        return {}


def enabled(root: str | Path) -> bool:
    return bool(_settings(Path(root)).get("telemetry", False))


def set_enabled(root: str | Path, on: bool) -> None:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with _lock:
        data = {**_settings(root), "telemetry": bool(on)}
        tmp = root / (SETTINGS + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(root / SETTINGS)


def clean(event: str, fields: dict) -> dict | None:
    """The event with only its allowed fields and values, or None for an unknown event."""
    allowed = EVENTS.get(event)
    if allowed is None:
        return None
    out: dict = {}
    for key, rule in allowed.items():
        value = fields.get(key)
        if rule == NUMBER and isinstance(value, (int, float)) and not isinstance(value, bool):
            out[key] = round(float(value), 2)
        elif rule == FLAG and isinstance(value, bool):
            out[key] = value
        elif isinstance(rule, set) and isinstance(value, str) and value in rule:
            out[key] = value
    return out


def record(root: str | Path, event: str, **fields) -> bool:
    """Append `event` when telemetry is on. Returns whether it was kept. Never raises."""
    try:
        root = Path(root)
        if not enabled(root):
            return False
        kept = clean(event, fields)
        if kept is None:
            return False
        line = json.dumps({"t": int(time.time()), "event": event, **kept})
        path = root / FILE
        with _lock:
            with open(path, "a") as f:
                f.write(line + "\n")
            if path.stat().st_size > MAX_BYTES:
                lines = path.read_text().splitlines()
                path.write_text("\n".join(lines[len(lines) // 2:]) + "\n")
        return True
    except Exception:
        return False


def events(root: str | Path) -> list[dict]:
    path = Path(root) / FILE
    out = []
    try:
        for line in path.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    return out


def summary(root: str | Path) -> dict:
    """Counts per event, how often renders and suggestions work out, and typical times."""
    log = events(root)
    counts: dict[str, int] = {}
    for e in log:
        counts[e["event"]] = counts.get(e["event"], 0) + 1

    def median(name: str, field: str) -> float | None:
        values = sorted(e[field] for e in log if e["event"] == name and field in e)
        return values[len(values) // 2] if values else None

    renders = counts.get("render_done", 0) + counts.get("render_failed", 0)
    shown = [e for e in log if e["event"] == "suggestion" and e.get("outcome") in ("kept", "put_back", "skipped")]
    return {
        "enabled": enabled(root),
        "events": len(log),
        "since": log[0]["t"] if log else None,
        "counts": counts,
        "render_success": round(counts.get("render_done", 0) / renders, 2) if renders else None,
        "suggestion_kept": round(sum(e.get("outcome") == "kept" for e in shown) / len(shown), 2) if shown else None,
        "median_job_seconds": median("job_done", "seconds"),
        "median_render_seconds": median("render_done", "seconds"),
    }


def clear(root: str | Path) -> None:
    (Path(root) / FILE).unlink(missing_ok=True)
