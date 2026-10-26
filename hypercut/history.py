"""Version history of a project's plan, kept on disk next to it (ADR 0021).

A job folder is a project: `plan.json` is the current edit, `history/` holds every saved version as a full
snapshot plus an index saying who made it, its name if the user gave one, and what changed in words, and
`draft.json` is the editor's autosave of edits not saved yet. Undo and redo move between versions and survive
a reload or a crash; going back to an old version adds a new one, so nothing is ever lost.

    commit(job_dir, plan, "edit")      # save a version (no-op if nothing changed)
    undo(job_dir) / redo(job_dir)      # -> the plan now current
    restore(job_dir, 3)                # make version 3 current again, as a new version
    name(job_dir, 3, "Good cut")       # name a version so it stands out (and is never pruned)

Snapshots are 20-150 KB, so whole copies are simpler and sturdier than a patch log. Pure file I/O: no
Claude, no rendering.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from hypercut import diff
from hypercut import plan as plan_mod
from hypercut.plan import EditPlan

HISTORY_DIR = "history"
INDEX = "index.json"
DRAFT = "draft.json"
# Unnamed versions beyond this many are pruned, oldest first. Named and pipeline versions are kept.
MAX_VERSIONS = 300

# pipeline: the first cut HyperCut made. edit: saved from the editor. assistant: a request the user
# accepted. review: fixes from the render review. restore: an older version made current again.
# render: graphics drawn and pictures fetched just before a render. import: loaded from elsewhere.
Kind = Literal["pipeline", "edit", "assistant", "review", "restore", "render", "import"]

_lock = threading.Lock()


class Version(BaseModel):
    id: int
    parent: int | None = None
    kind: Kind = "edit"
    created: float = Field(default_factory=time.time)
    label: str | None = None  # the user's name for it
    note: str | None = None  # e.g. the assistant request that made it
    changes: list[str] = []  # what changed from the parent, in words (`hypercut.diff`)
    duration: float = 0.0  # reel seconds


class Index(BaseModel):
    head: int | None = None
    versions: list[Version] = []
    redo: list[int] = []  # versions undone from, most recent last

    def get(self, vid: int) -> Version:
        for v in self.versions:
            if v.id == vid:
                return v
        raise KeyError(vid)


def _dir(job_dir: Path) -> Path:
    return Path(job_dir) / HISTORY_DIR


def _snapshot(job_dir: Path, vid: int) -> Path:
    return _dir(job_dir) / f"v{vid:04d}.json"


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def _read_index(job_dir: Path) -> Index:
    path = _dir(job_dir) / INDEX
    return Index.model_validate_json(path.read_text()) if path.is_file() else Index()


def _write_index(job_dir: Path, index: Index) -> None:
    _write_atomic(_dir(job_dir) / INDEX, index.model_dump_json(indent=2) + "\n")


def _save_plan(job_dir: Path, plan: EditPlan) -> None:
    _write_atomic(Path(job_dir) / "plan.json", plan.model_dump_json(indent=2) + "\n")


def load_version(job_dir: str | Path, vid: int) -> EditPlan:
    path = _snapshot(Path(job_dir), vid)
    if not path.is_file():
        raise KeyError(vid)
    return plan_mod.load(path)


def _same(a: EditPlan, b: EditPlan) -> bool:
    return a.model_dump(mode="json") == b.model_dump(mode="json")


def _add(job_dir: Path, index: Index, plan: EditPlan, kind: str, changes: list[str] | None,
         label: str | None, note: str | None) -> Version:
    parent = index.head
    if changes is None:
        changes = diff.explain(load_version(job_dir, parent), plan) if parent is not None else []
    vid = max((v.id for v in index.versions), default=0) + 1
    version = Version(id=vid, parent=parent, kind=kind, label=label, note=note, changes=changes[:60],
                      duration=round(plan.output_duration(), 2))
    _write_atomic(_snapshot(job_dir, vid), plan.model_dump_json(indent=2) + "\n")
    index.versions.append(version)
    index.head = vid
    _prune(job_dir, index)
    return version


def _prune(job_dir: Path, index: Index) -> None:
    keep = lambda v: v.label or v.kind == "pipeline" or v.id == index.head or v.id in index.redo  # noqa: E731
    extra = len(index.versions) - MAX_VERSIONS
    for v in list(index.versions):
        if extra <= 0:
            break
        if not keep(v):
            index.versions.remove(v)
            _snapshot(job_dir, v.id).unlink(missing_ok=True)
            extra -= 1
    alive = {v.id for v in index.versions}
    for v in index.versions:  # a pruned parent: point at the nearest surviving ancestor
        while v.parent is not None and v.parent not in alive:
            v.parent = next((p.parent for p in index.versions if p.id == v.parent), None)


def ensure(job_dir: str | Path) -> Index:
    """Start the history of a project that has a plan but none yet (jobs from before ADR 0021): the plan as
    the pipeline made it (`plan.base.json` when there is one) becomes version 1, edits since then version 2."""
    job_dir = Path(job_dir)
    with _lock:
        index = _read_index(job_dir)
        if index.versions or not (job_dir / "plan.json").is_file():
            return index
        current = plan_mod.load(job_dir / "plan.json")
        base_path = job_dir / "plan.base.json"
        base = plan_mod.load(base_path) if base_path.is_file() else current
        _add(job_dir, index, base, "pipeline", [], None, "HyperCut's first cut")
        if not _same(base, current):
            _add(job_dir, index, current, "edit", None, None, "Edits made before version history")
        _write_index(job_dir, index)
        return index


def commit(job_dir: str | Path, plan: EditPlan, kind: str = "edit", changes: list[str] | None = None,
           label: str | None = None, note: str | None = None) -> Version:
    """Make `plan` the current plan and record it as a new version, unless it is the same as the current
    one. `changes` defaults to an explanation of the difference. Clears redo and the autosaved draft."""
    job_dir = Path(job_dir)
    ensure(job_dir)
    with _lock:
        index = _read_index(job_dir)
        if index.head is not None and _same(load_version(job_dir, index.head), plan):
            version = index.get(index.head)
            if label and not version.label:
                version.label = label
                _write_index(job_dir, index)
        else:
            version = _add(job_dir, index, plan, kind, changes, label, note)
            index.redo = []
            _write_index(job_dir, index)
        _save_plan(job_dir, plan)
        (job_dir / DRAFT).unlink(missing_ok=True)
        return version


def undo(job_dir: str | Path) -> tuple[EditPlan, Version]:
    """Step back to the current version's parent. Raises LookupError at the first version."""
    job_dir = Path(job_dir)
    ensure(job_dir)
    with _lock:
        index = _read_index(job_dir)
        head = index.get(index.head) if index.head is not None else None
        if head is None or head.parent is None:
            raise LookupError("nothing to undo")
        index.redo.append(head.id)
        index.head = head.parent
        return _move(job_dir, index)


def redo(job_dir: str | Path) -> tuple[EditPlan, Version]:
    job_dir = Path(job_dir)
    ensure(job_dir)
    with _lock:
        index = _read_index(job_dir)
        if not index.redo:
            raise LookupError("nothing to redo")
        index.head = index.redo.pop()
        return _move(job_dir, index)


def _move(job_dir: Path, index: Index) -> tuple[EditPlan, Version]:
    plan = load_version(job_dir, index.head)
    _write_index(job_dir, index)
    _save_plan(job_dir, plan)
    (job_dir / DRAFT).unlink(missing_ok=True)
    return plan, index.get(index.head)


def restore(job_dir: str | Path, vid: int) -> Version:
    """Make an older version current again. It is added as a new version, so the versions after it stay."""
    job_dir = Path(job_dir)
    ensure(job_dir)
    index = _read_index(job_dir)
    old = index.get(vid)
    what = f"version {vid}" + (f" “{old.label}”" if old.label else "")
    return commit(job_dir, load_version(job_dir, vid), "restore", note=f"Went back to {what}")


def name(job_dir: str | Path, vid: int, label: str | None) -> Version:
    """Name (or with None / "" un-name) a version."""
    job_dir = Path(job_dir)
    ensure(job_dir)
    with _lock:
        index = _read_index(job_dir)
        version = index.get(vid)
        version.label = (label or "").strip()[:80] or None
        _write_index(job_dir, index)
        return version


def listing(job_dir: str | Path) -> dict:
    """What the editor shows: every version newest first, which is current, and whether undo/redo work."""
    index = ensure(job_dir)
    head = index.get(index.head) if index.head is not None else None
    return {
        "head": index.head,
        "can_undo": bool(head and head.parent is not None),
        "can_redo": bool(index.redo),
        "versions": [v.model_dump(mode="json") for v in reversed(index.versions)],
    }


# The editor's autosave: edits not saved as a version yet, so a closed tab or a crash loses nothing.

def save_draft(job_dir: str | Path, plan: EditPlan) -> dict:
    index = ensure(job_dir)
    record = {"saved": time.time(), "base": index.head, "plan": plan.model_dump(mode="json")}
    _write_atomic(Path(job_dir) / DRAFT, json.dumps(record) + "\n")
    return {"saved": record["saved"], "base": record["base"]}


def draft(job_dir: str | Path) -> dict | None:
    """The autosaved draft, if it differs from the current plan: {saved, base, plan, changes}."""
    job_dir = Path(job_dir)
    path = job_dir / DRAFT
    if not path.is_file() or not (job_dir / "plan.json").is_file():
        return None
    try:
        record = json.loads(path.read_text())
        plan = EditPlan.model_validate(record["plan"])
    except (ValueError, KeyError):
        path.unlink(missing_ok=True)  # a half-written or outdated draft is of no use
        return None
    current = plan_mod.load(job_dir / "plan.json")
    if _same(current, plan):
        path.unlink(missing_ok=True)
        return None
    return {**record, "plan": plan.model_dump(mode="json"), "changes": diff.explain(current, plan)}


def discard_draft(job_dir: str | Path) -> None:
    (Path(job_dir) / DRAFT).unlink(missing_ok=True)
