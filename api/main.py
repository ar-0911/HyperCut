"""FastAPI job server: `uvicorn api.main:app`. See docs/decisions/0701-*."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field

from api import assets, jobs, kits, recipes
from hypercut import plan as plan_mod
from hypercut import assistant, checks, diff, edit, explain, export, generate, brand, history, llm, modes, project, qa, review, run, suggest, telemetry, variants, vision
from hypercut.analyze import cuts as cutting
from hypercut.ingest import PROXY_FILE, IngestError, make_proxy, manifest
from hypercut.matte import MATTE_FILE
from hypercut.plan import EditPlan, Style


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    recover_interrupted()
    yield


app = FastAPI(title="HyperCut", lifespan=_lifespan)
# The web app calls the API straight from the browser (ADR 0802).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("HYPERCUT_WEB_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

INTERRUPTED = "HyperCut stopped while this was running (the app was closed or crashed). Try again."


def recover_interrupted() -> None:
    """Work that was running when the server stopped can't still be running: say so, so the editor offers
    a retry instead of waiting forever (ADR 0021)."""
    for job_id in jobs.all_ids():
        try:
            state = jobs.read(job_id)
        except (KeyError, ValueError):
            continue
        fields = {}
        if state.get("status") in ("queued", "running"):
            fields.update(status="error", error=INTERRUPTED, interrupted=True)
        for task in ("render", "matte", "export"):
            if state.get(task) == "running":
                fields.update({task: "error", f"{task}_error": INTERRUPTED})
        if state.get("qa") == "running":
            fields["qa"] = None
        if fields:
            jobs.write(job_id, **fields)


# Rendering is heavy; one at a time keeps a laptop usable.
_render_slot = threading.Semaphore(1)
# Uploads run in parallel threads; read-modify-write of the asset list must not interleave.
_assets_lock = threading.Lock()


def _job(job_id: str) -> dict:
    try:
        return jobs.read(job_id)
    except KeyError:
        raise HTTPException(404, "no such job") from None


def _plan_path(job_id: str) -> Path:
    return jobs.job_dir(job_id) / "plan.json"


def _base_path(job_id: str) -> Path:
    """The plan as the pipeline made it, kept on the first edit so it can be restored."""
    return jobs.job_dir(job_id) / "plan.base.json"


def _editable(job_id: str) -> dict:
    # Editing goes on during a render: the render works from a snapshot of the plan (ADR 0028).
    state = _job(job_id)
    if state["status"] != "done":
        raise HTTPException(409, f"job is {state['status']}; the plan can be edited once it is done")
    return state


def _media_names(plan: EditPlan) -> set[str]:
    names = {str(g.props["src"]) for g in plan.graphics if g.type in ("media", "motion") and g.props.get("src")}
    names |= {f for f in (plan.brand.logo, plan.brand.music, plan.brand.font) if f}
    return names | {b.src for b in plan.backgrounds if b.kind == "media" and b.src}


def _known_media(job_id: str, state: dict) -> set[str]:
    """Files a plan may show: the user's imports and the stock / generated files fetched for this job."""
    generated = {p.name for p in jobs.job_dir(job_id).glob("gen-*") if p.suffix in (".jpg", ".jpeg", ".png", ".webp", ".mp4")}
    branded = {p.name for p in jobs.job_dir(job_id).glob("brand-*")}  # a brand kit's files (ADR 0026)
    return {a["name"] for a in state.get("assets", [])} | generated | branded


MAX_CLIPS = 10


def _process(job_id: str, video: Path | list[Path], style: str, strategy: str, recipe: Style | None = None,
             pictures: bool = False, vision_provider: str | None = None, mode: str | None = None,
             kit: str | None = None) -> None:
    try:
        jobs.write(job_id, status="running", stage="ingest")
        run.run_pipeline(
            video, jobs.job_dir(job_id), style, strategy,
            on_stage=lambda s: jobs.write(job_id, stage=s), recipe=recipe, pictures=pictures,
            vision=vision_provider, mode=mode, kit=kits.kit_dir(kit) if kit else None,
        )
        state = jobs.write(job_id, status="done", stage="done", error=None)
        _count("job_done", seconds=time.time() - state.get("created", time.time()),
               reel_seconds=edit.reel_duration(plan_mod.load(_plan_path(job_id))))
    except Exception as e:
        state = jobs.write(job_id, status="error", error=str(e))
        _count("job_failed", stage=state.get("stage") or "unknown")


def _count(event: str, **fields) -> None:
    """Record a usage count when the person turned them on (ADR 0030); never footage, text or names."""
    telemetry.record(jobs.media_root(), event, **fields)


def _render(job_id: str) -> None:
    # The version being rendered, so the editor can say when the download is older than the edit.
    head = history.listing(jobs.job_dir(job_id))["head"]
    jobs.write(job_id, render_version=None, rendering_version=head)
    started = time.time()
    with _render_slot:
        try:
            directory = jobs.job_dir(job_id)
            run.render_plan(directory)
            # Unedited meanwhile: the render is of the current version (with what the render drew in).
            snapshot = directory / run.RENDER_PLAN
            if not snapshot.is_file() or plan_mod.load(directory / "plan.json") == plan_mod.load(snapshot):
                head = history.listing(directory)["head"]
            jobs.write(job_id, render="done", qa="running", render_version=head)
            _count("render_done", seconds=time.time() - started)
        except Exception as e:
            jobs.write(job_id, render="error", render_error=str(e))
            _count("render_failed")
            return
    # A render that exited cleanly is not yet a good file: inspect it (ADR 0023).
    try:
        result = qa.validate_job(jobs.job_dir(job_id))
        jobs.write(job_id, qa=result)
        _count("qa", ok=bool(result.get("ok")), failures=len([c for c in result.get("checks", []) if c.get("status") == "fail"]))
    except Exception as e:
        jobs.write(job_id, qa={"ok": None, "error": str(e)[:300]})


def _stale(job_id: str) -> None:
    """The plan changed: an earlier render no longer matches it. A render going on carries on with its snapshot
    (ADR 0028); the editor tells its version apart from the edit by `render_version`."""
    if jobs.read(job_id).get("render") != "running":
        jobs.write(job_id, render=None, render_error=None, qa=None)


_proxy_jobs: set[str] = set()  # jobs whose preview copy was started by this server process


def _start_proxy(job_id: str) -> None:
    with _assets_lock:
        if job_id in _proxy_jobs:
            return
        _proxy_jobs.add(job_id)

    def make() -> None:
        try:
            make_proxy(jobs.job_dir(job_id) / "normalized.mp4")
        except Exception:  # the editor keeps playing the full video
            pass

    threading.Thread(target=make, daemon=True).start()


_matte_jobs: set[str] = set()  # jobs whose cut-out is being made by this server process


def _make_matte(job_id: str) -> None:
    try:
        run.ensure_matte(jobs.job_dir(job_id), force=True)
        jobs.write(job_id, matte="done", matte_error=None)
    except Exception as e:
        jobs.write(job_id, matte="error", matte_error=str(e))
    finally:
        _matte_jobs.discard(job_id)


@app.post("/jobs", status_code=202)
def create_job(
    background: BackgroundTasks,
    video: UploadFile = File(...),
    style: str = Form(""),
    hook_strategy: Literal["cold_open", "trim"] = Form("cold_open"),
    recipe: str = Form(""),
    pictures: bool = Form(False),
    # Who describes frames of the footage (ADR 0024): nobody (local signals only), a local model, or Claude (opt-in:
    # frames leave the machine). Empty: the server's HYPERCUT_VISION, else nobody.
    vision: Literal["", "none", "ollama", "claude"] = Form(""),
    # What kind of video this is (ADR 0025): sets how it is edited. Empty: talking head.
    mode: Literal["", "talking_head", "podcast", "product_demo", "vlog"] = Form(""),
    # A brand kit's id (ADR 0026): its look, logo, music, end card and font go on the reel.
    kit: str = Form(""),
    # More clips of the same recording, joined after `video` in this order (ADR 0105).
    more: list[UploadFile] = File(default=[]),
):
    saved_style = recipes.get(recipe) if recipe else None
    if recipe and saved_style is None:
        raise HTTPException(422, f"no recipe called {recipe!r}")
    if kit and kits.kit_dir(kit) is None:
        raise HTTPException(422, f"no brand kit {kit!r}")
    job_id = jobs.new_id()
    directory = jobs.job_dir(job_id)
    directory.mkdir(parents=True)
    upload = directory / ("upload" + Path(video.filename or "").suffix.lower()[:8])
    with upload.open("wb") as f:
        shutil.copyfileobj(video.file, f)
    more = [m for m in more if m.filename]
    if len(more) + 1 > MAX_CLIPS:
        shutil.rmtree(directory, ignore_errors=True)
        raise HTTPException(422, f"at most {MAX_CLIPS} clips in one reel")
    clips: list[Path] = [upload]
    for i, extra in enumerate(more, start=2):
        clips.append(directory / (f"upload-{i}" + Path(extra.filename or "").suffix.lower()[:8]))
        with clips[-1].open("wb") as f:
            shutil.copyfileobj(extra.file, f)
    jobs.write(job_id, status="queued", stage=None, error=None, render=None, render_error=None,
               style=style or (f"recipe: {recipe}" if recipe else ""), hook_strategy=hook_strategy, filename=video.filename,
               pictures=pictures, vision=vision or None, mode=mode or None, kit=kit or None)
    background.add_task(_process, job_id, clips if len(clips) > 1 else upload, style, hook_strategy, saved_style,
                        pictures, vision or None, mode or None, kit or None)
    _count("job_created", mode=mode or "talking_head", kit=bool(kit), pictures=pictures, recipe=bool(recipe),
           style_prompt=bool(style))
    return {"id": job_id, "status": "queued"}


@app.post("/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: str, background: BackgroundTasks):
    """Run the pipeline again on the uploaded video of a job that failed or was interrupted."""
    state = _job(job_id)
    if state["status"] != "error":
        raise HTTPException(409, f"job is {state['status']}; only a failed job can be retried")
    upload = next(iter(sorted(jobs.job_dir(job_id).glob("upload.*"))), None) or next(
        iter(sorted(jobs.job_dir(job_id).glob("upload"))), None)
    if upload is None:
        raise HTTPException(409, "the uploaded video is gone; upload it again")
    extra = sorted(jobs.job_dir(job_id).glob("upload-*"), key=lambda p: int(p.stem.split("-")[1]) if p.stem.split("-")[1].isdigit() else 0)
    recipe = state.get("style", "")
    saved = recipes.get(recipe.removeprefix("recipe: ")) if recipe.startswith("recipe: ") else None
    jobs.write(job_id, status="queued", stage=None, error=None, interrupted=False)
    background.add_task(_process, job_id, [upload, *extra] if extra else upload, "" if saved else state.get("style", ""),
                        state.get("hook_strategy", "cold_open"), saved, bool(state.get("pictures")),
                        state.get("vision"), state.get("mode"),
                        state.get("kit") if state.get("kit") and kits.kit_dir(state["kit"]) else None)
    return {"id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    state = _job(job_id)
    path = _plan_path(job_id)
    state["plan"] = plan_mod.load(path).model_dump(mode="json") if path.is_file() else None
    base = _base_path(job_id)
    state["base_plan"] = plan_mod.load(base).model_dump(mode="json") if base.is_file() else state["plan"]
    state.setdefault("assets", [])
    # What ingest found in the upload (ADR 0104): the warnings are shown above the editor.
    facts = manifest.load(jobs.job_dir(job_id)) or {}
    state["manifest"] = {k: facts.get(k) for k in ("video", "audio", "warnings", "stages")} if facts else None
    state["files"] = sorted(p.name for p in jobs.job_dir(job_id).iterdir() if p.is_file() and p.name != "job.json")
    if state["status"] == "done" and PROXY_FILE not in state["files"]:
        _start_proxy(job_id)  # jobs from before the preview copy, and opened projects (ADR 0028)
    # What this machine can fetch for the editor's pictures, and what this video has spent on generating them.
    state["generation"] = {**generate.spent(jobs.job_dir(job_id)), "available": sorted(generate.available())}
    return state


@app.put("/jobs/{job_id}/plan")
def put_plan(job_id: str, plan: EditPlan, kind: history.Kind = "edit", note: str | None = None,
             label: str | None = None):
    """Save the plan as a new version (ADR 0021); an invalid plan gets a 422 from validation. `kind` says who
    made it (the editor, an accepted assistant request, review fixes), `note` the request, `label` a name."""
    state = _editable(job_id)
    missing = sorted(_media_names(plan) - _known_media(job_id, state))
    if missing:
        raise HTTPException(422, f"imported file not found in this job: {', '.join(missing)}")
    path, base = _plan_path(job_id), _base_path(job_id)
    if path.is_file() and not base.exists():
        shutil.copyfile(path, base)
    history.commit(jobs.job_dir(job_id), plan, kind, note=(note or "")[:300] or None, label=label)
    _count("edit_saved", kind=kind)
    _stale(job_id)
    return plan.model_dump(mode="json")


@app.post("/jobs/{job_id}/plan/restore")
def restore_plan(job_id: str):
    """Put back the plan the pipeline made, as a new version (the edits stay in the history)."""
    _editable(job_id)
    directory = jobs.job_dir(job_id)
    index = history.ensure(directory)
    first = next((v for v in index.versions if v.kind == "pipeline"), None)
    if first is not None:
        history.restore(directory, first.id)
        _stale(job_id)
    return plan_mod.load(_plan_path(job_id)).model_dump(mode="json")


# Version history (ADR 0021): every saved version, undo/redo that survives a reload, named versions.

def _history_dir(job_id: str) -> Path:
    state = _job(job_id)
    if state["status"] != "done" or not _plan_path(job_id).is_file():
        raise HTTPException(409, f"job is {state['status']}; there is no plan yet")
    return jobs.job_dir(job_id)


@app.get("/jobs/{job_id}/history")
def get_history(job_id: str):
    return history.listing(_history_dir(job_id))


@app.get("/jobs/{job_id}/history/{vid}")
def get_version(job_id: str, vid: int):
    directory = _history_dir(job_id)
    try:
        plan = history.load_version(directory, vid)
    except KeyError:
        raise HTTPException(404, "no such version") from None
    return {"plan": plan.model_dump(mode="json"), "changes_from_current": diff.explain(plan_mod.load(_plan_path(job_id)), plan)}


def _moved(job_id: str, step) -> dict:
    _editable(job_id)
    try:
        plan, version = step(jobs.job_dir(job_id))
    except LookupError as e:
        raise HTTPException(409, str(e)) from None
    _stale(job_id)
    return {"plan": plan.model_dump(mode="json"), "version": version.model_dump(mode="json"),
            **{k: v for k, v in history.listing(jobs.job_dir(job_id)).items() if k != "versions"}}


@app.post("/jobs/{job_id}/history/undo")
def undo(job_id: str):
    return _moved(job_id, history.undo)


@app.post("/jobs/{job_id}/history/redo")
def redo(job_id: str):
    return _moved(job_id, history.redo)


@app.post("/jobs/{job_id}/history/{vid}/restore")
def restore_version(job_id: str, vid: int):
    _editable(job_id)
    directory = jobs.job_dir(job_id)
    try:
        version = history.restore(directory, vid)
    except KeyError:
        raise HTTPException(404, "no such version") from None
    _stale(job_id)
    return {"plan": plan_mod.load(_plan_path(job_id)).model_dump(mode="json"), "version": version.model_dump(mode="json")}


class NameRequest(BaseModel):
    label: str | None = Field(default=None, max_length=80)


@app.patch("/jobs/{job_id}/history/{vid}")
def name_version(job_id: str, vid: int, req: NameRequest):
    try:
        return history.name(_history_dir(job_id), vid, req.label).model_dump(mode="json")
    except KeyError:
        raise HTTPException(404, "no such version") from None


@app.put("/jobs/{job_id}/draft")
def put_draft(job_id: str, plan: EditPlan):
    """The editor's autosave of unsaved edits, every few seconds; offered back when the editor reopens."""
    return history.save_draft(_history_dir(job_id), plan)


@app.get("/jobs/{job_id}/draft")
def get_draft(job_id: str):
    return {"draft": history.draft(_history_dir(job_id))}


@app.delete("/jobs/{job_id}/draft")
def delete_draft(job_id: str):
    history.discard_draft(_history_dir(job_id))
    return {"deleted": True}


@app.post("/jobs/{job_id}/checks")
def check_plan(job_id: str, plan: EditPlan):
    """Automatic checks of an (unsaved) plan: clipped words, leftover pauses, length, hook, visuals (ADR 0023)."""
    _job(job_id)
    return checks.report(plan, jobs.job_dir(job_id))


@app.get("/jobs/{job_id}/explain")
def explain_cut(job_id: str):
    """Why HyperCut's first cut looks the way it does (and the current edit, if it was changed since)."""
    directory = _history_dir(job_id)
    index = history.ensure(directory)
    first = next((v for v in index.versions if v.kind == "pipeline"), None)
    plan = history.load_version(directory, first.id) if first else plan_mod.load(_plan_path(job_id))
    index = vision.load(directory / vision.INDEX_FILE)
    return {"first_cut": explain.first_cut(plan, index), "current": explain.first_cut(plan_mod.load(_plan_path(job_id)), index)}


@app.post("/jobs/{job_id}/assets", status_code=201)
def upload_asset(job_id: str, file: UploadFile = File(...)):
    """Import a picture or a clip to use as B-roll in the editor."""
    state = _job(job_id)
    if state["status"] != "done":
        raise HTTPException(409, f"job is {state['status']}; import files once it is done")
    directory = jobs.job_dir(job_id)
    tmp = directory / f"upload-asset-{uuid.uuid4().hex[:8]}.tmp"
    with tmp.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        record = assets.add(directory, tmp, file.filename or "", len(state.get("assets", [])))
    except assets.AssetError as e:
        raise HTTPException(422, str(e)) from None
    with _assets_lock:
        current = jobs.read(job_id).get("assets", [])
        jobs.write(job_id, assets=current + [record])
    return record


@app.delete("/jobs/{job_id}/assets/{name}")
def delete_asset(job_id: str, name: str):
    state = _job(job_id)
    if not any(a["name"] == name for a in state.get("assets", [])):
        raise HTTPException(404, "no such file")
    path = _plan_path(job_id)
    if path.is_file() and name in _media_names(plan_mod.load(path)):
        raise HTTPException(409, "this file is still on the timeline; remove it there and save first")
    with _assets_lock:
        current = jobs.read(job_id).get("assets", [])
        jobs.write(job_id, assets=[a for a in current if a["name"] != name])
    (jobs.job_dir(job_id) / name).unlink(missing_ok=True)
    return {"deleted": name}


class AssistRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)
    plan: EditPlan
    playhead: float = Field(default=0, ge=0)
    selected: str | None = None


@app.post("/jobs/{job_id}/assistant")
def assistant_edit(job_id: str, req: AssistRequest):
    """Turn a plain-language request into an edited plan. Nothing is saved; the editor applies the result
    as one undoable step."""
    state = _job(job_id)
    if state["status"] != "done":
        raise HTTPException(409, f"job is {state['status']}; wait for the plan before editing")
    try:
        wav = jobs.job_dir(job_id) / "audio.wav"
        result = assistant.assist(req.plan, req.instruction, req.playhead, state.get("assets", []), req.selected,
                                  str(wav) if wav.is_file() else None)
    except llm.LLMError as e:
        raise HTTPException(502, f"the assistant could not answer: {str(e)[:300]}") from None
    return {"plan": result.plan.model_dump(mode="json"), "message": result.message, "changes": result.changes,
            "explanation": result.explanation}


@app.post("/jobs/{job_id}/recut")
def recut_plan(job_id: str, plan: EditPlan):
    """Rebuild the cuts of the plan it is sent from its `style.pacing` (how much pause to keep, fillers).
    Uses the job's audio for silence detection; nothing is saved."""
    _job(job_id)
    wav = jobs.job_dir(job_id) / "audio.wav"
    return cutting.recut(plan, str(wav) if wav.is_file() else None).model_dump(mode="json")


@app.get("/jobs/{job_id}/suggestion")
def suggestion(job_id: str):
    """One change worth trying on the saved edit, for the editor's first steps (ADR 0029). No Claude call;
    nothing is saved. `suggestion` is null when nothing stands out."""
    state = _job(job_id)
    if state["status"] != "done":
        raise HTTPException(409, f"job is {state['status']}; wait for the plan first")
    wav = jobs.job_dir(job_id) / "audio.wav"
    found = suggest.suggest(plan_mod.load(_plan_path(job_id)), str(wav) if wav.is_file() else None)
    if found is None:
        return {"suggestion": None}
    return {"suggestion": {"kind": found.kind, "label": found.label, "why": found.why, "changes": found.changes,
                           "plan": found.plan.model_dump(mode="json")}}


@app.post("/jobs/{job_id}/render", status_code=202)
def render_job(job_id: str, background: BackgroundTasks):
    state = _job(job_id)
    if state["status"] != "done":
        raise HTTPException(409, f"job is {state['status']}; wait for the plan before rendering")
    if state.get("render") == "running":
        raise HTTPException(409, "already rendering")
    jobs.write(job_id, render="running", render_error=None)
    background.add_task(_render, job_id)
    return {"id": job_id, "render": "running"}


@app.post("/jobs/{job_id}/matte", status_code=202)
def make_matte(job_id: str, background: BackgroundTasks):
    """Cut the speaker out of the video for green-screen effects (ADR 0901), once. The editor asks for it
    when the user turns the effects on; a render makes it itself if it is still missing."""
    state = _job(job_id)
    if state["status"] != "done":
        raise HTTPException(409, f"job is {state['status']}; wait for the plan first")
    if (jobs.job_dir(job_id) / MATTE_FILE).is_file():
        jobs.write(job_id, matte="done", matte_error=None)
        return {"id": job_id, "matte": "done"}
    with _assets_lock:
        start = job_id not in _matte_jobs
        _matte_jobs.add(job_id)
    if start:
        jobs.write(job_id, matte="running", matte_error=None)
        background.add_task(_make_matte, job_id)
    return {"id": job_id, "matte": "running"}


class GenerateRequest(BaseModel):
    plan: EditPlan
    graphic_id: str | None = None
    prompt: str | None = Field(default=None, max_length=1000)


@app.post("/jobs/{job_id}/generate")
def generate_assets(job_id: str, req: GenerateRequest):
    """Fetch the stock footage and generated pictures / clips the plan waits for (ADR 0016); with `graphic_id`, fetch
    that one again (a new seed, or `prompt`). Files land in the job folder; the plan is returned, not saved."""
    state = _job(job_id)
    if state["status"] != "done":
        raise HTTPException(409, f"job is {state['status']}; wait for the plan first")
    plan = req.plan
    if req.graphic_id:
        if not any(g.id == req.graphic_id for g in plan.graphics):
            raise HTTPException(404, "no such graphic")
        plan = generate.regenerate(plan, req.graphic_id, req.prompt)
    directory = jobs.job_dir(job_id)
    plan = generate.generate(plan.model_copy(deep=True), directory)
    return {"plan": plan.model_dump(mode="json"), "generation": {**generate.spent(directory), "available": sorted(generate.available())}}


class RecipeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    style: Style
    note: str = Field(default="", max_length=200)


@app.get("/generation")
def generation_sources():
    """Which kinds of picture this machine can fetch (stock / image / video); empty without keys (ADR 0020)."""
    return {"available": sorted(generate.available())}


@app.get("/modes")
def list_modes():
    """The editing modes the upload page offers as "What are you making?" (ADR 0025)."""
    return {"modes": modes.listing(), "default": modes.DEFAULT_MODE}


@app.get("/recipes")
def list_recipes():
    return {"recipes": recipes.all_recipes()}


@app.post("/recipes", status_code=201)
def save_recipe(req: RecipeRequest):
    try:
        return recipes.save(req.name, req.style, req.note)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@app.delete("/recipes/{name}")
def delete_recipe(name: str):
    if not recipes.delete(name):
        raise HTTPException(404, "no such recipe")
    return {"deleted": name}


# What of a job's state a project file keeps (ADR 0027): never ids, paths or run state.
PROJECT_STATE = ("filename", "style", "hook_strategy", "mode", "assets", "pictures", "vision")


@app.get("/jobs/{job_id}/project")
def export_project(job_id: str, footage: bool = True):
    """The whole edit as one `.hypercut` file: plan, versions and files, and the footage unless `footage=false`."""
    state = _job(job_id)
    if not _plan_path(job_id).is_file():
        raise HTTPException(409, "the job has no edit yet")
    out = jobs.job_dir(job_id) / f"project-{uuid.uuid4().hex[:8]}.hypercut"
    try:
        project.pack(jobs.job_dir(job_id), out, footage=footage, job={k: state[k] for k in PROJECT_STATE if k in state})
    except project.ProjectError as e:
        raise HTTPException(409, str(e)) from None
    name = Path(state.get("filename") or "project").stem + ".hypercut"
    _count("project_saved", footage=footage)
    return FileResponse(out, filename=name, media_type="application/zip", background=BackgroundTask(out.unlink, missing_ok=True))


@app.post("/projects", status_code=201)
def import_project(project_file: UploadFile = File(...), source: UploadFile | None = File(None)):
    """Open a `.hypercut` file as a new job. One saved without footage needs `source`, the original video, which
    must match the project's SHA-256."""
    job_id = jobs.new_id()
    directory = jobs.job_dir(job_id)
    directory.mkdir(parents=True)
    incoming = directory / "incoming.hypercut"
    try:
        with incoming.open("wb") as f:
            shutil.copyfileobj(project_file.file, f)
        video = None
        if source is not None and source.filename:
            video = directory / ("upload" + Path(source.filename).suffix.lower()[:8])
            with video.open("wb") as f:
                shutil.copyfileobj(source.file, f)
        meta = project.unpack(incoming, directory, video)
    except (project.ProjectError, IngestError) as e:
        shutil.rmtree(directory, ignore_errors=True)
        raise HTTPException(422, str(e)) from None
    finally:
        incoming.unlink(missing_ok=True)
    kept = {k: v for k, v in (meta.get("job") or {}).items() if k in PROJECT_STATE}
    jobs.write(job_id, status="done", stage="done", error=None, render=None, render_error=None, **kept)
    _count("project_opened")
    return {"id": job_id, "footage": meta.get("footage"), "versions": len(history.listing(directory)["versions"])}


@app.get("/kits")
def list_kits():
    return {"kits": kits.all_kits()}


@app.post("/kits", status_code=201)
async def create_kit(
    name: str = Form(..., min_length=1, max_length=60),
    # The look to keep: the current style of this job, else an explicit Style JSON, else the defaults.
    from_job: str = Form(""),
    style: str = Form(""),
    logo: UploadFile | None = File(None),
    music: UploadFile | None = File(None),
    font: UploadFile | None = File(None),
    logo_corner: Literal["top_left", "top_right", "bottom_left", "bottom_right"] = Form("top_right"),
    logo_size: float = Form(0.16),
    end_card: str = Form("", max_length=80),
    music_volume: float = Form(0.25),
    duck: float = Form(0.3),
    font_name: str = Form("", max_length=40),
):
    """Save a brand kit: the look of an edit plus a logo, music, a font and an end card line."""
    if from_job:
        path = _plan_path(from_job)
        if not path.is_file():
            raise HTTPException(404, "no plan for that job")
        look = plan_mod.load(path).style
    else:
        try:
            look = Style.model_validate_json(style) if style else Style()
        except ValueError as e:
            raise HTTPException(422, f"style: {e}") from None
    files = {}
    for kind, upload in (("logo", logo), ("music", music), ("font", font)):
        if upload is not None and upload.filename:
            files[kind] = (upload.filename, await upload.read())
    try:
        kit_brand = plan_mod.Brand(logo_corner=logo_corner, logo_size=logo_size, end_card=" ".join(end_card.split()),
                                   music_volume=music_volume, duck=duck,
                                   font_name=(" ".join(font_name.split()) or "Brand font") if "font" in files else "")
        kit_id = kits.create(brand.Kit(name=" ".join(name.split()), look=brand.look_of(look), brand=kit_brand), files)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return {"id": kit_id, **brand.summary(kits.kit_dir(kit_id))}


@app.get("/kits/{kit_id}/files/{name}")
def kit_file(kit_id: str, name: str):
    path = kits.kit_dir(kit_id)
    if path is None or name not in {f for f in brand.files_of(path).values() if f}:
        raise HTTPException(404, "no such file")
    return FileResponse(path / name)


@app.delete("/kits/{kit_id}")
def delete_kit(kit_id: str):
    if not kits.delete(kit_id):
        raise HTTPException(404, "no such brand kit")
    return {"deleted": kit_id}


class KitRequest(BaseModel):
    kit: str


@app.post("/jobs/{job_id}/kit")
def apply_kit(job_id: str, req: KitRequest):
    """Put a brand kit on the current edit, as a new version."""
    state = _job(job_id)
    path = _plan_path(job_id)
    if state["status"] != "done" or not path.is_file():
        raise HTTPException(409, "the job has no edit yet")
    folder = kits.kit_dir(req.kit)
    if folder is None:
        raise HTTPException(404, "no such brand kit")
    plan = plan_mod.load(path)
    changes = brand.apply(plan, folder, jobs.job_dir(job_id))
    history.commit(jobs.job_dir(job_id), plan, "edit", changes=changes, note=changes[0])
    _count("kit_applied")
    return {"plan": plan.model_dump(mode="json"), "changes": changes}


def _clone(job_id: str, plan: EditPlan, label: str) -> str:
    """A new, editable job with the same footage and files as `job_id` and its own plan."""
    state = _job(job_id)
    source = jobs.job_dir(job_id)
    new_id = jobs.new_id()
    target = jobs.job_dir(new_id)
    target.mkdir(parents=True)
    keep = {"normalized.mp4", "audio.wav", "transcript.json", "transcript.srt", MATTE_FILE}
    for p in source.iterdir():
        if p.is_file() and (p.name in keep or p.name.startswith(("asset-", "gen-"))):
            try:
                os.link(p, target / p.name)
            except OSError:
                shutil.copyfile(p, target / p.name)
    history.commit(target, plan, "pipeline", changes=[], note=f"A variant of {state.get('filename') or job_id}: {label}")
    jobs.write(new_id, status="done", stage="done", error=None, render=None, render_error=None,
               style=state.get("style", ""), hook_strategy=plan.hook.strategy,
               filename=f"{state.get('filename') or job_id} ({label})", assets=state.get("assets", []), variant_of=job_id)
    return new_id


@app.post("/jobs/{job_id}/variants", status_code=201)
def make_variants(job_id: str, plan: EditPlan):
    """New jobs from this edit (ADR 0018): one per other hook candidate, and 30 s / 45 s cuts. Each opens in the editor."""
    _editable(job_id)
    made = []
    for label, p in variants.variants(plan):
        made.append({"id": _clone(job_id, p, label), "label": label, "duration": round(edit.reel_duration(p), 1)})
    return {"variants": made}


@app.post("/jobs/{job_id}/review")
def review_render(job_id: str):
    """Claude looks at frames of the latest render and proposes fixes (ADR 0019). Nothing is saved."""
    state = _job(job_id)
    video = jobs.job_dir(job_id) / "output.mp4"
    if state.get("render") != "done" or not video.is_file():
        raise HTTPException(409, "render the current edit first; the review looks at the rendered video")
    try:
        result = review.review(plan_mod.load(_plan_path(job_id)), video)
    except llm.LLMError as e:
        raise HTTPException(502, f"the review could not run: {str(e)[:300]}") from None
    return {
        "summary": result.summary,
        "issues": [{"at": i.at, "severity": i.severity, "problem": i.problem, "fixable": bool(i.ops)} for i in result.issues],
        "plan": result.plan.model_dump(mode="json"),
        "changes": result.changes,
    }


def _export(job_id: str, overlays: bool) -> None:
    directory = jobs.job_dir(job_id)
    try:
        clip = None
        if overlays:
            with _render_slot:
                clip = run.render_plan(directory, export.OVERLAYS, extra_args=["--overlays", "1"])
        export.export(directory, overlays=clip)
        jobs.write(job_id, export="done", export_error=None)
    except Exception as e:
        jobs.write(job_id, export="error", export_error=str(e)[:500])


class ExportRequest(BaseModel):
    overlays: bool = True


@app.post("/jobs/{job_id}/export", status_code=202)
def export_job(job_id: str, req: ExportRequest, background: BackgroundTasks):
    """Build hypercut-export.zip for Final Cut, Resolve and Premiere (ADR 0017) from the saved plan."""
    state = _job(job_id)
    if state["status"] != "done":
        raise HTTPException(409, f"job is {state['status']}; wait for the plan first")
    if state.get("export") == "running":
        raise HTTPException(409, "already exporting")
    jobs.write(job_id, export="running", export_error=None)
    background.add_task(_export, job_id, req.overlays)
    return {"id": job_id, "export": "running"}


@app.get("/jobs/{job_id}/files/{name}")
def get_file(job_id: str, name: str):
    _job(job_id)
    root = jobs.job_dir(job_id).resolve()
    path = (root / name).resolve()
    if path.parent != root or name == "job.json" or not path.is_file():
        raise HTTPException(404, "no such file")
    return FileResponse(path)


# Usage counts (ADR 0030): off until turned on, kept in the media folder, never sent anywhere.

class TelemetrySetting(BaseModel):
    enabled: bool


class TelemetryEvent(BaseModel):
    event: str = Field(max_length=40)
    fields: dict = Field(default_factory=dict)


@app.get("/telemetry")
def telemetry_summary():
    """Whether counting is on, what has been counted, and every event with the only fields it can hold."""
    return {**telemetry.summary(jobs.media_root()), "fields": {e: sorted(f) for e, f in telemetry.EVENTS.items()}}


@app.put("/telemetry")
def telemetry_setting(req: TelemetrySetting):
    telemetry.set_enabled(jobs.media_root(), req.enabled)
    return telemetry.summary(jobs.media_root())


@app.post("/telemetry/events", status_code=204)
def telemetry_event(req: TelemetryEvent):
    """What the web app counts itself (a suggestion kept, a share). Unknown events and fields are dropped."""
    if req.event in telemetry.CLIENT_EVENTS:
        _count(req.event, **req.fields)


@app.get("/telemetry/file")
def telemetry_file():
    path = jobs.media_root() / telemetry.FILE
    if not path.is_file():
        raise HTTPException(404, "nothing recorded")
    return FileResponse(path, media_type="application/x-ndjson", filename="hypercut-usage.jsonl")


@app.delete("/telemetry")
def telemetry_clear():
    telemetry.clear(jobs.media_root())
    return telemetry.summary(jobs.media_root())
