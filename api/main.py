"""FastAPI job server: `uvicorn api.main:app`. See docs/decisions/0701-*."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
import shutil
import threading
import uuid
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api import assets, jobs, recipes
from hypercut import plan as plan_mod
from hypercut import assistant, checks, diff, edit, explain, export, generate, history, llm, qa, review, run, variants, vision
from hypercut.analyze import cuts as cutting
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
    state = _job(job_id)
    if state["status"] != "done":
        raise HTTPException(409, f"job is {state['status']}; the plan can be edited once it is done")
    if state.get("render") == "running":
        raise HTTPException(409, "a render is running; wait for it to finish")
    return state


def _media_names(plan: EditPlan) -> set[str]:
    names = {str(g.props["src"]) for g in plan.graphics if g.type in ("media", "motion") and g.props.get("src")}
    return names | {b.src for b in plan.backgrounds if b.kind == "media" and b.src}


def _known_media(job_id: str, state: dict) -> set[str]:
    """Files a plan may show: the user's imports and the stock / generated files fetched for this job."""
    generated = {p.name for p in jobs.job_dir(job_id).glob("gen-*") if p.suffix in (".jpg", ".jpeg", ".png", ".webp", ".mp4")}
    return {a["name"] for a in state.get("assets", [])} | generated


def _process(job_id: str, video: Path, style: str, strategy: str, recipe: Style | None = None,
             pictures: bool = False, vision_provider: str | None = None) -> None:
    try:
        jobs.write(job_id, status="running", stage="ingest")
        run.run_pipeline(
            video, jobs.job_dir(job_id), style, strategy,
            on_stage=lambda s: jobs.write(job_id, stage=s), recipe=recipe, pictures=pictures,
            vision=vision_provider,
        )
        jobs.write(job_id, status="done", stage="done", error=None)
    except Exception as e:
        jobs.write(job_id, status="error", error=str(e))


def _render(job_id: str) -> None:
    with _render_slot:
        try:
            run.render_plan(jobs.job_dir(job_id))
            jobs.write(job_id, render="done", qa="running")
        except Exception as e:
            jobs.write(job_id, render="error", render_error=str(e))
            return
    # A render that exited cleanly is not yet a good file: inspect it (ADR 0023).
    try:
        result = qa.validate_job(jobs.job_dir(job_id))
        jobs.write(job_id, qa=result)
    except Exception as e:
        jobs.write(job_id, qa={"ok": None, "error": str(e)[:300]})


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
):
    saved_style = recipes.get(recipe) if recipe else None
    if recipe and saved_style is None:
        raise HTTPException(422, f"no recipe called {recipe!r}")
    job_id = jobs.new_id()
    directory = jobs.job_dir(job_id)
    directory.mkdir(parents=True)
    upload = directory / ("upload" + Path(video.filename or "").suffix.lower()[:8])
    with upload.open("wb") as f:
        shutil.copyfileobj(video.file, f)
    jobs.write(job_id, status="queued", stage=None, error=None, render=None, render_error=None,
               style=style or (f"recipe: {recipe}" if recipe else ""), hook_strategy=hook_strategy, filename=video.filename,
               pictures=pictures, vision=vision or None)
    background.add_task(_process, job_id, upload, style, hook_strategy, saved_style, pictures, vision or None)
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
    recipe = state.get("style", "")
    saved = recipes.get(recipe.removeprefix("recipe: ")) if recipe.startswith("recipe: ") else None
    jobs.write(job_id, status="queued", stage=None, error=None, interrupted=False)
    background.add_task(_process, job_id, upload, "" if saved else state.get("style", ""),
                        state.get("hook_strategy", "cold_open"), saved, bool(state.get("pictures")),
                        state.get("vision"))
    return {"id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    state = _job(job_id)
    path = _plan_path(job_id)
    state["plan"] = plan_mod.load(path).model_dump(mode="json") if path.is_file() else None
    base = _base_path(job_id)
    state["base_plan"] = plan_mod.load(base).model_dump(mode="json") if base.is_file() else state["plan"]
    state.setdefault("assets", [])
    state["files"] = sorted(p.name for p in jobs.job_dir(job_id).iterdir() if p.is_file() and p.name != "job.json")
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
    jobs.write(job_id, render=None, render_error=None, qa=None)  # any earlier render is stale
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
        jobs.write(job_id, render=None, render_error=None, qa=None)
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
    jobs.write(job_id, render=None, render_error=None, qa=None)
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
    jobs.write(job_id, render=None, render_error=None, qa=None)
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
