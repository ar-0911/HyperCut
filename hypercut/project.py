"""Portable projects: a whole edit in one `.hypercut` file, opened on any machine (ADR 0027).

    pack(job_dir, "talk.hypercut", footage=True)        # plan, versions, files; the footage unless footage=False
    unpack("talk.hypercut", new_job_dir, source=None)   # a project without footage needs the original video back
    find_source(job_dir_or_manifest, ["~/Videos"])      # the original by size and SHA-256, wherever it moved

A `.hypercut` file is a zip: `project.json` (what it holds and the original's SHA-256 from the manifest, ADR 0104),
the plan and its history, the transcript, the visual index, and every file the plan shows (imports, stock and
generated media, brand files). With `footage`, also `normalized.mp4` and `audio.wav`, so it opens and renders as is.
Without, it is small, and opening it asks for the original video, which is recognised by its hash, re-normalised,
and checked against the project before the edit is used.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath

from hypercut import plan as plan_mod
from hypercut.ingest import manifest as media_manifest

FORMAT = "hypercut-project"
VERSION = 1
PROJECT_FILE = "project.json"
FOOTAGE = ("normalized.mp4", "audio.wav", "matte.webm")  # the cut-out, when made, is slow to make again
# What a project carries besides the footage: the edit, its history and what HyperCut knows about the source.
EDIT_FILES = ("plan.json", "plan.base.json", "transcript.json", "transcript.srt", "visual_index.json",
              media_manifest.FILE, "draft.json")
MEDIA_PREFIXES = ("asset-", "gen-", "brand-")
SKIP_DIRS = {"frames"}  # sampled frames are rebuilt when needed
MAX_ENTRIES = 5000


class ProjectError(ValueError):
    """The project can't be opened; the message is safe to show."""


def _sha256(path: Path) -> str:
    return media_manifest.sha256(path)


def pack(job_dir: str | Path, out: str | Path, footage: bool = True, job: dict | None = None) -> Path:
    """Write the job at `job_dir` as a `.hypercut` file at `out`. `job` is the job's state worth keeping (name,
    imports list, mode); never paths or ids."""
    job_dir, out = Path(job_dir), Path(out)
    if not (job_dir / "plan.json").is_file():
        raise ProjectError("this job has no edit yet")
    facts = media_manifest.load(job_dir) or {}
    names = [n for n in EDIT_FILES if (job_dir / n).is_file()]
    names += sorted(p.name for p in job_dir.iterdir() if p.is_file() and p.name.startswith(MEDIA_PREFIXES))
    if footage:
        names += [n for n in FOOTAGE if (job_dir / n).is_file()]
    history_dir = job_dir / "history"
    if history_dir.is_dir():
        names += sorted(f"history/{p.name}" for p in history_dir.iterdir() if p.is_file() and p.suffix == ".json")
    meta = {
        "format": FORMAT,
        "version": VERSION,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "footage": footage and (job_dir / "normalized.mp4").is_file(),
        "original": facts.get("original"),
        "normalized_sha256": _sha256(job_dir / "normalized.mp4") if (job_dir / "normalized.mp4").is_file() else None,
        "job": job or {},
        "files": names,
    }
    tmp = out.with_name(out.name + ".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(PROJECT_FILE, json.dumps(meta, indent=2))
        for name in names:
            # Video and audio don't compress; storing them is faster.
            kind = zipfile.ZIP_STORED if name.endswith((".mp4", ".mov", ".webm", ".jpg", ".png", ".mp3", ".m4a")) else zipfile.ZIP_DEFLATED
            z.write(job_dir / name, name, compress_type=kind)
    tmp.replace(out)
    return out


def read_meta(project: str | Path) -> dict:
    try:
        with zipfile.ZipFile(project) as z:
            meta = json.loads(z.read(PROJECT_FILE))
    except (zipfile.BadZipFile, KeyError, ValueError, OSError):
        raise ProjectError("this is not a HyperCut project file") from None
    if meta.get("format") != FORMAT:
        raise ProjectError("this is not a HyperCut project file")
    if meta.get("version", 0) > VERSION:
        raise ProjectError("this project was made by a newer HyperCut; update to open it")
    return meta


def _safe(name: str) -> bool:
    p = PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts and len(p.parts) <= 2 and (len(p.parts) == 1 or p.parts[0] == "history")


def unpack(project: str | Path, job_dir: str | Path, source: str | Path | None = None, ingest=None) -> dict:
    """Open a `.hypercut` file into the empty folder `job_dir`. Returns the project's metadata.

    A project without footage needs `source`, the original video: it must have the SHA-256 the project recorded
    (else ProjectError), and is normalised again with `ingest` (default `hypercut.ingest.ingest`).
    """
    project, job_dir = Path(project), Path(job_dir)
    meta = read_meta(project)
    job_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(project) as z:
        entries = [i for i in z.infolist() if not i.is_dir() and i.filename != PROJECT_FILE]
        if len(entries) > MAX_ENTRIES:
            raise ProjectError("the project holds too many files")
        for info in entries:
            if not _safe(info.filename):
                raise ProjectError(f"the project holds a file outside it: {info.filename}")
            target = job_dir / info.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    if not (job_dir / "plan.json").is_file():
        raise ProjectError("the project has no edit in it")

    if not (job_dir / "normalized.mp4").is_file():
        if source is None:
            raise ProjectError("this project was saved without its footage; add the original video to open it")
        want = (meta.get("original") or {}).get("sha256")
        if want and _sha256(Path(source)) != want:
            raise ProjectError("that video is not the one this project was made from")
        if ingest is None:
            from hypercut.ingest import ingest
        saved = media_manifest.load(job_dir)  # keep the project's own facts (and their warnings)
        ingest(source, job_dir)
        if saved:
            media_manifest.save(job_dir, saved)
    # The plan names the footage by path; point it at this copy.
    for name in ["plan.json", "plan.base.json"] + [f"history/{p.name}" for p in (job_dir / "history").glob("v*.json")]:
        path = job_dir / name
        if path.is_file():
            _repoint(path, job_dir / "normalized.mp4")
    return meta


def _repoint(path: Path, video: Path) -> None:
    data = json.loads(path.read_text())
    plan = data.get("plan") if isinstance(data.get("plan"), dict) else data  # a history version wraps the plan
    if isinstance(plan.get("source"), dict):
        plan["source"]["path"] = str(video)
        plan_mod.EditPlan.model_validate(plan)
        path.write_text(json.dumps(data, indent=2))


def find_source(original: dict, folders: list[str | Path], limit: int = 20000) -> Path | None:
    """The original video (from a manifest's `original`: bytes and sha256) under `folders`, wherever it was moved
    or renamed: files of the same size are hashed until one matches."""
    size, want = original.get("bytes"), original.get("sha256")
    if not size or not want:
        return None
    seen = 0
    for folder in folders:
        for path in Path(folder).expanduser().rglob("*"):
            seen += 1
            if seen > limit:
                return None
            try:
                if path.is_file() and path.stat().st_size == size and _sha256(path) == want:
                    return path
            except OSError:
                continue
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hypercut.project", description="Pack a job folder as a .hypercut file, or open one.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack")
    p.add_argument("job_dir")
    p.add_argument("out")
    p.add_argument("--no-footage", action="store_true", help="leave the video out (opening it asks for the original)")
    u = sub.add_parser("unpack")
    u.add_argument("project")
    u.add_argument("job_dir")
    u.add_argument("--source", help="the original video, for a project saved without footage")
    u.add_argument("--find", action="append", default=[], help="folder to look for the original in (by its hash)")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "pack":
            print(pack(args.job_dir, args.out, footage=not args.no_footage))
        else:
            source = args.source
            if source is None and args.find:
                found = find_source(read_meta(args.project).get("original") or {}, args.find)
                source = str(found) if found else None
            unpack(args.project, args.job_dir, source)
            print(args.job_dir)
    except ProjectError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
