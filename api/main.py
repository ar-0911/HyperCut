"""FastAPI job server: `uvicorn api.main:app`. See docs/decisions/0701-*."""

from __future__ import annotations

import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api import assets, jobs
from hypercut import plan as plan_mod
from hypercut import assistant, llm, run
from hypercut.plan import EditPlan

app = FastAPI(title="HyperCut")
# The web app calls the API straight from the browser (ADR 0802).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("HYPERCUT_WEB_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    return {str(g.props.get("src", "")) for g in plan.graphics if g.type == "media"}


def _process(job_id: str, video: Path, style: str, strategy: str) -> None:
    try:
        jobs.write(job_id, status="running", stage="ingest")
        run.run_pipeline(
            video, jobs.job_dir(job_id), style, strategy,
            on_stage=lambda s: jobs.write(job_id, stage=s),
        )
        jobs.write(job_id, status="done", stage="done", error=None)
    except Exception as e:
        jobs.write(job_id, status="error", error=str(e))


def _render(job_id: str) -> None:
    with _render_slot:
        try:
            run.render_plan(jobs.job_dir(job_id))
            jobs.write(job_id, render="done")
        except Exception as e:
            jobs.write(job_id, render="error", render_error=str(e))


@app.post("/jobs", status_code=202)
def create_job(
    background: BackgroundTasks,
    video: UploadFile = File(...),
    style: str = Form(""),
    hook_strategy: Literal["cold_open", "trim"] = Form("cold_open"),
):
    job_id = jobs.new_id()
    directory = jobs.job_dir(job_id)
    directory.mkdir(parents=True)
    upload = directory / ("upload" + Path(video.filename or "").suffix.lower()[:8])
    with upload.open("wb") as f:
        shutil.copyfileobj(video.file, f)
    jobs.write(job_id, status="queued", stage=None, error=None, render=None, render_error=None,
               style=style, hook_strategy=hook_strategy, filename=video.filename)
    background.add_task(_process, job_id, upload, style, hook_strategy)
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
    return state


@app.put("/jobs/{job_id}/plan")
def put_plan(job_id: str, plan: EditPlan):
    """Replace the plan; an invalid plan gets a 422 from validation."""
    state = _editable(job_id)
    known = {a["name"] for a in state.get("assets", [])}
    missing = sorted(_media_names(plan) - known)
    if missing:
        raise HTTPException(422, f"imported file not found in this job: {', '.join(missing)}")
    path, base = _plan_path(job_id), _base_path(job_id)
    if path.is_file() and not base.exists():
        shutil.copyfile(path, base)
    plan_mod.save(plan, path)
    jobs.write(job_id, render=None, render_error=None)  # any earlier render is stale
    return plan.model_dump(mode="json")


@app.post("/jobs/{job_id}/plan/restore")
def restore_plan(job_id: str):
    """Put back the plan the pipeline made, dropping every edit."""
    _editable(job_id)
    base = _base_path(job_id)
    if base.is_file():
        shutil.copyfile(base, _plan_path(job_id))
        jobs.write(job_id, render=None, render_error=None)
    return plan_mod.load(_plan_path(job_id)).model_dump(mode="json")


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
        result = assistant.assist(req.plan, req.instruction, req.playhead, state.get("assets", []), req.selected)
    except llm.LLMError as e:
        raise HTTPException(502, f"the assistant could not answer: {str(e)[:300]}") from None
    return {"plan": result.plan.model_dump(mode="json"), "message": result.message, "changes": result.changes}


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


@app.get("/jobs/{job_id}/files/{name}")
def get_file(job_id: str, name: str):
    _job(job_id)
    root = jobs.job_dir(job_id).resolve()
    path = (root / name).resolve()
    if path.parent != root or name == "job.json" or not path.is_file():
        raise HTTPException(404, "no such file")
    return FileResponse(path)
