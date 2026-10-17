"""FastAPI job server: `uvicorn api.main:app`. See docs/decisions/0701-*."""

from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from api import jobs
from hypercut import plan as plan_mod
from hypercut import run
from hypercut.plan import EditPlan

app = FastAPI(title="HyperCut")

# Rendering is heavy; one at a time keeps a laptop usable.
_render_slot = threading.Semaphore(1)


def _job(job_id: str) -> dict:
    try:
        return jobs.read(job_id)
    except KeyError:
        raise HTTPException(404, "no such job") from None


def _plan_path(job_id: str) -> Path:
    return jobs.job_dir(job_id) / "plan.json"


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
    state["files"] = sorted(p.name for p in jobs.job_dir(job_id).iterdir() if p.is_file() and p.name != "job.json")
    return state


@app.put("/jobs/{job_id}/plan")
def put_plan(job_id: str, plan: EditPlan):
    """Replace the plan; an invalid plan gets a 422 from validation."""
    state = _job(job_id)
    if state["status"] != "done":
        raise HTTPException(409, f"job is {state['status']}; the plan can be edited once it is done")
    if state.get("render") == "running":
        raise HTTPException(409, "a render is running; wait for it to finish")
    plan_mod.save(plan, _plan_path(job_id))
    jobs.write(job_id, render=None, render_error=None)  # any earlier render is stale
    return plan.model_dump(mode="json")


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
