import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hypercut import run
from hypercut.ingest import IngestError
from hypercut.plan import EditPlan, Hook, HookCandidate, Reframe, ReframeKey, Source, Transcript, Word

SOURCE = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=20)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HYPERCUT_MEDIA", str(tmp_path))
    from api.main import app

    return TestClient(app)


@pytest.fixture
def fake_stages(monkeypatch):
    calls = {}

    def ingest(video, job_dir):
        calls["ingest"] = Path(video).name
        (Path(job_dir) / "normalized.mp4").write_bytes(b"video")
        (Path(job_dir) / "audio.wav").write_bytes(b"wav")
        return SOURCE, Path(job_dir) / "normalized.mp4", Path(job_dir) / "audio.wav"

    def analyze(transcript, source, style, audio_wav=None, strategy="cold_open"):
        calls["strategy"] = strategy
        calls["style"] = style.name
        hook = Hook(strategy=strategy, candidates=[
            HookCandidate(start=0, end=2, text="a", score=0.9), HookCandidate(start=3, end=5, text="b", score=0.5)])
        return EditPlan(source=source, transcript=transcript, style=style, hook=hook)

    monkeypatch.setattr(run, "ingest", ingest)
    monkeypatch.setattr(run, "transcribe", lambda wav: Transcript(words=[Word(text="hi", start=0, end=1)]))
    monkeypatch.setattr(run, "reframe", lambda mp4, source: Reframe(keys=[ReframeKey(t=0, cx=0.4, cy=0.5)]))
    monkeypatch.setattr(run, "style_from_prompt", _style)
    monkeypatch.setattr(run, "analyze", analyze)
    return calls


def _style(prompt):
    from hypercut.plan import Style

    return Style(name="calm" if prompt else "bold_creator")


def _submit(client, **data):
    r = client.post("/jobs", files={"video": ("clip.mov", b"bytes")}, data=data)
    assert r.status_code == 202
    return r.json()["id"]


def _wait(client, job_id, key="status", done=("done", "error")):
    for _ in range(100):
        body = client.get(f"/jobs/{job_id}").json()
        if body[key] in done:
            return body
        time.sleep(0.02)
    raise AssertionError(body)


def test_pipeline_job(client, fake_stages):
    job_id = _submit(client, style="calm", hook_strategy="trim")
    body = _wait(client, job_id)
    assert body["status"] == "done" and body["stage"] == "done" and body["error"] is None
    assert body["plan"]["style"]["name"] == "calm"
    assert body["plan"]["reframe"]["keys"][0]["cx"] == 0.4
    assert fake_stages["strategy"] == "trim" and fake_stages["ingest"] == "upload.mov"
    assert "plan.json" in body["files"] and "job.json" not in body["files"]


def test_stage_error_is_reported(client, fake_stages, monkeypatch):
    def bad(video, job_dir):
        raise IngestError("Video is 4.0s long; the minimum is 10s")

    monkeypatch.setattr(run, "ingest", bad)
    body = _wait(client, _submit(client))
    assert body["status"] == "error" and "minimum is 10s" in body["error"] and body["plan"] is None


def test_unknown_job_and_bad_strategy(client):
    assert client.get("/jobs/000000000000").status_code == 404
    assert client.get("/jobs/..").status_code == 404
    r = client.post("/jobs", files={"video": ("c.mp4", b"x")}, data={"hook_strategy": "nope"})
    assert r.status_code == 422


def test_put_plan_validates_and_saves(client, fake_stages):
    job_id = _submit(client)
    plan = _wait(client, job_id)["plan"]
    plan["hook"]["chosen"] = 1
    assert client.put(f"/jobs/{job_id}/plan", json=plan).status_code == 200
    assert client.get(f"/jobs/{job_id}").json()["plan"]["hook"]["chosen"] == 1

    plan["hook"]["chosen"] = 9
    assert client.put(f"/jobs/{job_id}/plan", json=plan).status_code == 422
    assert client.get(f"/jobs/{job_id}").json()["plan"]["hook"]["chosen"] == 1


def test_plan_and_render_rejected_before_done(client):
    from api import jobs

    job_id = jobs.new_id()
    jobs.job_dir(job_id).mkdir(parents=True)
    jobs.write(job_id, status="running", stage="transcribe")
    plan = EditPlan(source=SOURCE).model_dump(mode="json")
    assert client.put(f"/jobs/{job_id}/plan", json=plan).status_code == 409
    assert client.post(f"/jobs/{job_id}/render").status_code == 409


def test_render_and_download(client, fake_stages, monkeypatch):
    seen = {}

    def render(job_dir):
        seen["dir"] = job_dir
        (Path(job_dir) / "output.mp4").write_bytes(b"mp4data")
        return Path(job_dir) / "output.mp4"

    monkeypatch.setattr(run, "render_plan", render)
    job_id = _submit(client)
    _wait(client, job_id)
    assert client.post(f"/jobs/{job_id}/render").status_code == 202
    assert _wait(client, job_id, "render", ("done", "error"))["render"] == "done"
    r = client.get(f"/jobs/{job_id}/files/output.mp4")
    assert r.status_code == 200 and r.content == b"mp4data"


def test_render_failure_and_stale_render(client, fake_stages, monkeypatch):
    def boom(job_dir):
        raise RuntimeError("render failed: no chrome")

    monkeypatch.setattr(run, "render_plan", boom)
    job_id = _submit(client)
    plan = _wait(client, job_id)["plan"]
    client.post(f"/jobs/{job_id}/render")
    body = _wait(client, job_id, "render", ("done", "error"))
    assert body["render"] == "error" and "no chrome" in body["render_error"]
    client.put(f"/jobs/{job_id}/plan", json=plan)
    assert client.get(f"/jobs/{job_id}").json()["render"] is None


def test_render_requires_done_job(client):
    assert client.post("/jobs/000000000000/render").status_code == 404


def test_files_are_confined(client, fake_stages):
    job_id = _submit(client)
    _wait(client, job_id)
    assert client.get(f"/jobs/{job_id}/files/job.json").status_code == 404
    assert client.get(f"/jobs/{job_id}/files/%2e%2e%2fother").status_code == 404
    assert client.get(f"/jobs/{job_id}/files/missing.txt").status_code == 404
    assert client.get(f"/jobs/{job_id}/files/plan.json").status_code == 200
