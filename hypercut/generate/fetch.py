"""Fetch the pictures and clips the plan asks for (ADR 0016).

A visual whose props carry `generate` and no `src` yet is filled in here:

    {"kind": "stock", "query": "aerial city at night", "media": "video" | "image" | "any"}   real stock footage
    {"kind": "image", "prompt": "..."}                                                     a generated still
    {"kind": "video", "prompt": "..."}                                                     a still, then animated

plus optional "look" (one line every prompt of the reel shares, so assets match) and "seed". The file lands in
the job folder as `gen-<hash>.<ext>` and the graphic gets `src`, `kind`, `duration` and, for stock, its credit;
the renderer's `media` graphic (and the full-screen motion graphic) then show it. Results are cached by their
request, so re-renders never pay twice, and every paid call is checked against a per-job budget
(HYPERCUT_GEN_BUDGET_USD, default 2) kept in `generate.json`.

Anything that can't be fetched (no backend, budget spent, an error, no stock shot fits) falls back: a picture or
footage becomes a drawn illustration of its brief; a motion moment keeps its 3D scene.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from hypercut.generate import backends, stock
from hypercut.generate.backends import Backend, GenerateError
from hypercut.plan import EditPlan, Graphic

log = logging.getLogger(__name__)

LEDGER = "generate.json"
DEFAULT_BUDGET = 2.0
PARALLEL = 3
KINDS = ("stock", "image", "video")
SUFFIX = (
    "Vertical 9:16 frame, the main subject in the middle third. Photographic or high-end 3D render quality, "
    "natural light, shallow depth of field. No text, no captions, no logos, no watermarks, no people's faces."
)
VIDEO_SUFFIX = "Slow, smooth camera move; the subject moves naturally and physically. No text, no logos, no faces."


def budget() -> float:
    try:
        return max(0.0, float(os.environ.get("HYPERCUT_GEN_BUDGET_USD", DEFAULT_BUDGET)))
    except ValueError:
        return DEFAULT_BUDGET


def available() -> set[str]:
    """Which kinds of asset this machine can fetch right now."""
    kinds = {"stock"} if stock.enabled() else set()
    if backends.configured() is not None:
        kinds.add("image")
        if backends.video_enabled():
            kinds.add("video")
    return kinds


def request_of(g: Graphic) -> dict | None:
    req = g.props.get("generate")
    if g.type not in ("media", "motion") or not isinstance(req, dict) or req.get("kind") not in KINDS:
        return None
    return req


def pending(plan: EditPlan) -> list[Graphic]:
    """Graphics still waiting for their file (not yet fetched and not given up on)."""
    return [g for g in plan.graphics if (req := request_of(g)) and not g.props.get("src") and not req.get("failed")]


def regenerate(plan: EditPlan, graphic_id: str, prompt: str | None = None) -> EditPlan:
    """A copy of the plan where one graphic will be fetched again (a new seed; a new prompt or query if given)."""
    plan = plan.model_copy(deep=True)
    for g in plan.graphics:
        req = g.props.get("generate")
        if g.id != graphic_id or not isinstance(req, dict) or req.get("kind") not in KINDS:
            continue
        if g.type not in ("media", "motion"):  # it fell back to a drawing or text: make it a picture again
            keep = ("title", "brief", "label", "fit", "move")
            g.type, g.props = "media", {k: v for k, v in g.props.items() if k in keep} | {"title": g.props.get("title") or g.props.get("text", "")}
        req = {k: v for k, v in req.items() if k not in ("failed", "file", "model", "cost")}
        req["seed"] = random.randint(1, 2**31 - 1)
        if prompt is not None and prompt.strip():
            req["query" if req["kind"] == "stock" else "prompt"] = prompt.strip()[:1000]
        g.props = {k: v for k, v in g.props.items() if k not in ("src", "credit", "credit_url", "credit_required")}
        g.props["generate"] = req
    return plan


def _key(req: dict, model: str) -> str:
    fields = {k: req.get(k) for k in ("kind", "prompt", "query", "media", "look", "seed")}
    return hashlib.sha256(json.dumps([fields, model], sort_keys=True).encode()).hexdigest()[:16]


def _said(plan: EditPlan, g: Graphic) -> str:
    return " ".join(w.text for w in plan.transcript.words if g.start - 1 <= w.start < g.end + 1)


class Ledger:
    """What this job has spent on generation, shared by the threads of one run."""

    def __init__(self, job_dir: Path, limit: float):
        self.path = job_dir / LEDGER
        self.limit = limit
        self.lock = threading.Lock()
        try:
            self.data = json.loads(self.path.read_text())
        except (FileNotFoundError, ValueError):
            self.data = {"spent": 0.0, "items": []}

    def reserve(self, cost: float) -> None:
        with self.lock:
            if self.data["spent"] + cost > self.limit + 1e-9:
                raise GenerateError(f"generation budget of ${self.limit:.2f} for this video is used up")
            self.data["spent"] = round(self.data["spent"] + cost, 4)
            self._save()

    def note(self, item: dict) -> None:
        with self.lock:
            self.data["items"].append(item)
            self._save()

    def refund(self, cost: float) -> None:
        with self.lock:
            self.data["spent"] = round(max(0.0, self.data["spent"] - cost), 4)
            self._save()

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2))
        tmp.replace(self.path)


def _prompt(req: dict, suffix: str) -> str:
    return " ".join(x for x in (str(req.get("prompt") or "").strip(), str(req.get("look") or "").strip(), suffix) if x)


def _paid(ledger: Ledger, cost: float, make):
    """Run a paid call; give the money back to the budget if it fails."""
    ledger.reserve(cost)
    try:
        return make()
    except Exception:
        ledger.refund(cost)
        raise


def fetch_one(plan: EditPlan, g: Graphic, job_dir: Path, backend: Backend | None, ledger: Ledger, choose=None) -> dict:
    """Fetch the file for one graphic. Returns the props to merge in. Raises GenerateError when it can't."""
    req = request_of(g)
    assert req is not None
    kind = req["kind"]
    if kind == "stock":
        if not stock.enabled():
            raise GenerateError("no stock library is set up")
        query = str(req.get("query") or "").strip()
        if not query:
            raise GenerateError("no search words")
        key = _key(req, "stock")
        cached = sorted(job_dir.glob(f"gen-{key}.*"))
        meta_path = job_dir / f"gen-{key}.json"
        if cached and meta_path.is_file():
            return json.loads(meta_path.read_text())
        media = req.get("media") if req.get("media") in ("video", "image", "any") else "any"
        brief = str(g.props.get("brief") or g.props.get("title") or query)
        pick = (choose or stock.choose)(stock.search(query, media), brief, _said(plan, g))
        if pick is None:
            raise GenerateError(f"no stock shot fits {query!r}")
        path, duration = stock.fetch(pick, job_dir / f"gen-{key}")
        props = {"src": path.name, "kind": pick.kind, "credit": pick.credit, "credit_url": pick.credit_url,
                 "credit_required": pick.credit_required}
        if duration is not None:
            props["duration"] = duration
        meta_path.write_text(json.dumps(props))
        ledger.note({"file": path.name, "kind": "stock", "query": query, "cost": 0, "credit": pick.credit})
        return props

    if backend is None:
        raise GenerateError("no image generator is set up (FAL_KEY or HYPERCUT_GEN_LOCAL)")
    if not str(req.get("prompt") or "").strip():
        raise GenerateError("no prompt")
    seed = req.get("seed") if isinstance(req.get("seed"), int) else None
    model = getattr(backend, "image_model", backend.name)
    key = _key({**req, "kind": "image"}, model)
    still = job_dir / f"gen-{key}.jpg"
    if not still.is_file():
        tmp = still.with_suffix(".part.jpg")
        made = _paid(ledger, backend.image_cost(), lambda: backend.image(_prompt(req, SUFFIX), tmp, seed))
        tmp.replace(still)
        ledger.note({"file": still.name, "kind": "image", "model": made.model, "prompt": req.get("prompt"), "cost": made.cost})
    if kind == "image":
        return {"src": still.name, "kind": "image"}

    vmodel = getattr(backend, "video_model", backend.name)
    vkey = _key(req, vmodel)
    clip = job_dir / f"gen-{vkey}.mp4"
    if not clip.is_file():
        tmp = clip.with_suffix(".part.mp4")
        made = _paid(ledger, backend.video_cost(), lambda: backend.video(_prompt(req, VIDEO_SUFFIX), still, tmp, seed))
        tmp.replace(clip)
        ledger.note({"file": clip.name, "kind": "video", "model": made.model, "prompt": req.get("prompt"), "cost": made.cost})
    return {"src": clip.name, "kind": "video", "duration": float(backends.CLIP_SECONDS), "poster": still.name}


def generate(plan: EditPlan, job_dir: str | Path, backend: Backend | None = None, draw=None, choose=None,
             limit: float | None = None) -> EditPlan:
    """Fill in every pending asset of the plan (in place, and returned). Failures fall back (see module doc)."""
    job_dir = Path(job_dir)
    todo = pending(plan)
    if not todo:
        return plan
    backend = backend if backend is not None else backends.configured()
    ledger = Ledger(job_dir, budget() if limit is None else limit)

    def one(g: Graphic) -> tuple[Graphic, dict | None, str]:
        try:
            return g, fetch_one(plan, g, job_dir, backend, ledger, choose), ""
        except Exception as e:  # noqa: BLE001 - one missing asset never fails the edit
            log.warning("could not fetch %s: %s", g.id, e)
            return g, None, str(e)[:300]

    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        results = list(pool.map(one, todo))
    failed: list[Graphic] = []
    for g, props, error in results:
        if props is not None:
            g.props = {**g.props, **props}
            g.props["generate"] = {**g.props["generate"], "file": props["src"]}
        else:
            g.props = {**g.props, "generate": {**g.props["generate"], "failed": error}}
            failed.append(g)
    fallback(plan, [g for g in failed if g.type == "media"], draw)
    return plan


def fallback(plan: EditPlan, failed: list[Graphic], draw=None) -> None:
    """Pictures and footage that couldn't be fetched become drawn illustrations of their brief (in place)."""
    if not failed:
        return
    from hypercut.analyze.visuals import illustrate

    briefs = [str(g.props.get("brief") or g.props.get("title") or "") for g in failed]
    try:
        drawn = (draw or illustrate)(briefs)
    except Exception as e:  # noqa: BLE001
        log.warning("fallback drawings failed: %s", e)
        drawn = [None] * len(failed)
    gone = set()
    for g, brief, art in zip(failed, briefs, drawn):
        title = str(g.props.get("title") or "")
        if art is not None and brief:
            g.type, g.props = "illustration", {**art, "title": title, "brief": brief, "generate": g.props["generate"]}
        elif title:
            g.type, g.props = "kinetic_text", {"text": title, "generate": g.props["generate"]}
        else:
            gone.add(g.id)
    plan.graphics = [g for g in plan.graphics if g.id not in gone]


def spent(job_dir: str | Path) -> dict:
    """The job's generation ledger: {"spent": dollars, "budget": dollars, "items": [...]}."""
    try:
        data = json.loads((Path(job_dir) / LEDGER).read_text())
    except (FileNotFoundError, ValueError):
        data = {"spent": 0.0, "items": []}
    return {**data, "budget": budget()}
