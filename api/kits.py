"""Brand kits on disk (ADR 0026): `media/kits/<id>/kit.json` plus the kit's logo, music and font, local like
everything else. The kit itself is `hypercut.brand`; this module only stores and lists them."""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from api import jobs
from hypercut import brand

MAX_KITS = 30


def root() -> Path:
    return jobs.media_root() / "kits"


def kit_dir(kit_id: str) -> Path | None:
    """The folder of a kit, or None for an id that isn't one (ids are generated, never paths)."""
    if not re.fullmatch(r"[a-z0-9-]{1,48}", kit_id or ""):
        return None
    path = root() / kit_id
    return path if (path / brand.KIT_FILE).is_file() else None


def all_kits() -> list[dict]:
    out = []
    for path in sorted(root().glob(f"*/{brand.KIT_FILE}")) if root().is_dir() else []:
        try:
            out.append({"id": path.parent.name, **brand.summary(path.parent)})
        except ValueError:
            continue  # a broken kit.json is skipped, not fatal
    return out


def create(kit: brand.Kit, files: dict[str, tuple[str, bytes]]) -> str:
    """Store a new kit with its files ({"logo": (original name, bytes)}); returns its id."""
    if len(all_kits()) >= MAX_KITS:
        raise ValueError(f"up to {MAX_KITS} brand kits; delete one first")
    for kind, (name, data) in files.items():
        brand.check_file(kind, name, len(data))
    slug = re.sub(r"[^a-z0-9]+", "-", kit.name.lower()).strip("-")[:32] or "kit"
    kit_id = f"{slug}-{uuid.uuid4().hex[:6]}"
    path = root() / kit_id
    path.mkdir(parents=True)
    for kind, (name, data) in files.items():
        stored = kind + Path(name).suffix.lower()
        (path / stored).write_bytes(data)
        setattr(kit.brand, kind, stored)
    brand.save(kit, path)
    return kit_id


def delete(kit_id: str) -> bool:
    path = kit_dir(kit_id)
    if path is None:
        return False
    shutil.rmtree(path)
    return True
