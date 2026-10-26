"""Brand kits: one look and one set of brand files, reused on every reel (ADR 0026).

    kit = make_kit("Acme", style, logo="logo.png", music="bed.mp3", end_card="Follow Acme")   # in a kit folder
    changes = apply(plan, kit_dir, job_dir)      # copies the files next to the video, sets plan.brand and the look

A kit is a folder holding `kit.json` and its files (logo, music, font). It carries the LOOK of a style (captions,
graphics colours and theme, how cuts look), not how the video is edited: pacing, zooms, effects and the editing mode
stay the reel's own, so one kit works for a podcast clip and a product demo alike. Applying a kit copies its files
into the job as `brand-<hash>.<ext>`, so a project keeps working if the kit is later changed or deleted.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from pydantic import Field

from hypercut.plan import Brand, EditPlan, Style, _Model

KIT_FILE = "kit.json"
LOOK = ("caption", "graphics", "transitions")  # the parts of a style a kit carries
FILES = {
    "logo": ({".png", ".jpg", ".jpeg", ".webp", ".svg"}, 5_000_000),
    "music": ({".mp3", ".m4a", ".aac", ".wav", ".ogg"}, 40_000_000),
    "font": ({".ttf", ".otf", ".woff", ".woff2"}, 5_000_000),
}


class Kit(_Model):
    name: str
    look: dict = Field(default_factory=dict)  # {"caption": {...}, "graphics": {...}, "transitions": {...}}
    brand: Brand = Brand()  # file fields name files in the kit folder


def look_of(style: Style) -> dict:
    data = style.model_dump(mode="json")
    return {k: data[k] for k in LOOK}


def check_file(kind: str, name: str, size: int) -> None:
    """Raise ValueError when a file can't be a kit's `kind` (logo, music, font)."""
    if kind not in FILES:
        raise ValueError(f"unknown kit file {kind!r}")
    exts, cap = FILES[kind]
    ext = Path(name).suffix.lower()
    if ext not in exts:
        raise ValueError(f"a {kind} must be one of {', '.join(sorted(exts))}")
    if size > cap:
        raise ValueError(f"the {kind} is over {cap // 1_000_000} MB")


def load(kit_dir: str | Path) -> Kit:
    return Kit.model_validate_json((Path(kit_dir) / KIT_FILE).read_text())


def save(kit: Kit, kit_dir: str | Path) -> None:
    kit_dir = Path(kit_dir)
    kit_dir.mkdir(parents=True, exist_ok=True)
    tmp = kit_dir / (KIT_FILE + ".tmp")
    tmp.write_text(kit.model_dump_json(indent=2))
    tmp.replace(kit_dir / KIT_FILE)


def _copy(src: Path, job_dir: Path) -> str:
    digest = hashlib.sha256(src.read_bytes()).hexdigest()[:12]
    name = f"brand-{digest}{src.suffix.lower()}"
    if not (job_dir / name).exists():
        shutil.copyfile(src, job_dir / name)
    return name


def apply(plan: EditPlan, kit_dir: str | Path, job_dir: str | Path) -> list[str]:
    """Put the kit at `kit_dir` on `plan`, in place; its files are copied into `job_dir`. Returns what changed."""
    kit_dir, job_dir = Path(kit_dir), Path(job_dir)
    kit = load(kit_dir)
    brand = kit.brand.model_copy(update={"name": kit.name})
    for field in ("logo", "music", "font"):
        name = getattr(kit.brand, field)
        path = kit_dir / name if name else None
        setattr(brand, field, _copy(path, job_dir) if path and path.is_file() else None)
    if not brand.font:
        brand.font_name = ""
    style = plan.style.model_dump()
    for part, values in kit.look.items():
        if part in LOOK and isinstance(values, dict):
            style[part] = {**style[part], **values}
    if brand.font_name:
        style["caption"]["font"] = brand.font_name
    new_style = Style.model_validate(style)
    changes = [f"Applied the brand kit “{kit.name}”"]
    if new_style != plan.style:
        changes.append("Captions, colours and cuts now follow the kit")
    plan.style, plan.brand = new_style, brand
    changes += [what for what, on in (("Logo in the corner", brand.logo), ("Music under the voice", brand.music),
                                      (f"End card “{brand.end_card}”", brand.end_card), (f"Font {brand.font_name}", brand.font_name)) if on]
    return changes


def files_of(kit_dir: str | Path) -> dict[str, str | None]:
    kit = load(kit_dir)
    return {f: getattr(kit.brand, f) for f in ("logo", "music", "font")}


def summary(kit_dir: str | Path) -> dict:
    """What the kits list shows."""
    kit = load(kit_dir)
    caption = kit.look.get("caption", {})
    graphics = kit.look.get("graphics", {})
    return {
        "name": kit.name,
        "logo": kit.brand.logo,
        "music": bool(kit.brand.music),
        "font": kit.brand.font_name or None,
        "end_card": kit.brand.end_card,
        "caption_font": caption.get("font"),
        "colors": [c for c in (graphics.get("accent_color"), caption.get("highlight_color")) if c],
    }
