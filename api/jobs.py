"""Job state: one JSON file per job under media/<job_id>/job.json. No database."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

JOB_ID = re.compile(r"^[0-9a-f]{12}$")
_lock = threading.Lock()


def media_root() -> Path:
    return Path(os.environ.get("HYPERCUT_MEDIA", Path(__file__).resolve().parent.parent / "media"))


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def job_dir(job_id: str) -> Path:
    if not JOB_ID.match(job_id):
        raise KeyError(job_id)
    return media_root() / job_id


def read(job_id: str) -> dict:
    path = job_dir(job_id) / "job.json"
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise KeyError(job_id) from None


def write(job_id: str, **fields) -> dict:
    """Merge `fields` into the job file atomically and return the new state."""
    with _lock:
        path = job_dir(job_id) / "job.json"
        state = json.loads(path.read_text()) if path.exists() else {"id": job_id, "created": time.time()}
        state.update(fields, updated=time.time())
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2))
        tmp.replace(path)
        return state


def all_ids() -> list[str]:
    root = media_root()
    return sorted(p.name for p in root.iterdir() if JOB_ID.match(p.name) and (p / "job.json").is_file()) if root.is_dir() else []
