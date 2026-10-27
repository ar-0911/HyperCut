import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hypercut import run
from hypercut.ingest import IngestError
from hypercut.vision import VisualIndex
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

    def analyze(transcript, source, style, audio_wav=None, strategy="cold_open", visuals=False, pictures=False):
        calls["strategy"] = strategy
        calls["pictures"] = pictures
        calls["style"] = style.name
        hook = Hook(strategy=strategy, candidates=[
            HookCandidate(start=0, end=2, text="a", score=0.9), HookCandidate(start=3, end=5, text="b", score=0.5)])
        return EditPlan(source=source, transcript=transcript, style=style, hook=hook)

    monkeypatch.setattr(run, "ingest", ingest)
    monkeypatch.setattr(run, "transcribe", lambda wav: Transcript(words=[Word(text="hi", start=0, end=1)]))
    monkeypatch.setattr(run, "reframe", lambda mp4, source: Reframe(keys=[ReframeKey(t=0, cx=0.4, cy=0.5)]))
    monkeypatch.setattr(run, "style_from_prompt", _style)
    monkeypatch.setattr(run, "analyze", analyze)
    monkeypatch.setattr(run, "build_index", lambda *a: VisualIndex(duration=SOURCE.duration))
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


def _done_job(client, fake_stages):
    job_id = _submit(client)
    _wait(client, job_id)
    return job_id


def test_cors_allows_the_web_app(client):
    r = client.options("/jobs/000000000000", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "PUT"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_base_plan_kept_and_restored(client, fake_stages):
    job_id = _done_job(client, fake_stages)
    body = client.get(f"/jobs/{job_id}").json()
    assert body["base_plan"] == body["plan"] and body["assets"] == []
    plan = body["plan"]
    plan["hook"]["chosen"] = 1
    client.put(f"/jobs/{job_id}/plan", json=plan)
    plan["hook"]["chosen"] = 0
    plan["zooms"] = [{"start": 1, "end": 2}]
    client.put(f"/jobs/{job_id}/plan", json=plan)
    body = client.get(f"/jobs/{job_id}").json()
    assert body["base_plan"]["hook"]["chosen"] == 0 and body["base_plan"]["zooms"] == []
    restored = client.post(f"/jobs/{job_id}/plan/restore").json()
    assert restored["zooms"] == [] and client.get(f"/jobs/{job_id}").json()["plan"]["zooms"] == []


def test_import_image_and_video_assets(client, fake_stages, monkeypatch):
    from api import assets

    def fake_prepare(src, out):
        out.write_bytes(b"mp4")
        return 12.5

    monkeypatch.setattr(assets, "prepare_video", fake_prepare)
    job_id = _done_job(client, fake_stages)
    img = client.post(f"/jobs/{job_id}/assets", files={"file": ("Product Shot.PNG", b"png")}).json()
    vid = client.post(f"/jobs/{job_id}/assets", files={"file": ("beach.mov", b"mov")}).json()
    assert img["kind"] == "image" and img["name"].endswith(".png") and img["label"] == "Product Shot"
    assert vid["kind"] == "video" and vid["name"].endswith(".mp4") and vid["duration"] == 12.5
    assert assets.is_asset_name(img["name"]) and assets.is_asset_name(vid["name"])
    body = client.get(f"/jobs/{job_id}").json()
    assert [a["name"] for a in body["assets"]] == [img["name"], vid["name"]]
    assert not any(f.endswith(".tmp") for f in body["files"])
    assert client.get(f"/jobs/{job_id}/files/{vid['name']}").content == b"mp4"

    bad = client.post(f"/jobs/{job_id}/assets", files={"file": ("notes.txt", b"x")})
    assert bad.status_code == 422 and "image" in bad.json()["detail"]

    # A media graphic must point at an imported file.
    plan = body["plan"]
    plan["graphics"] = [{"id": "m1", "type": "media", "start": 1, "end": 3, "props": {"src": "asset-ffffffffffff.png", "kind": "image"}}]
    assert client.put(f"/jobs/{job_id}/plan", json=plan).status_code == 422
    plan["graphics"][0]["props"]["src"] = img["name"]
    assert client.put(f"/jobs/{job_id}/plan", json=plan).status_code == 200
    assert client.delete(f"/jobs/{job_id}/assets/{img['name']}").status_code == 409
    assert client.delete(f"/jobs/{job_id}/assets/{vid['name']}").status_code == 200
    assert [a["name"] for a in client.get(f"/jobs/{job_id}").json()["assets"]] == [img["name"]]


def test_assistant_endpoint_returns_an_unsaved_plan(client, fake_stages, monkeypatch):
    from hypercut import llm

    job_id = _done_job(client, fake_stages)
    plan = client.get(f"/jobs/{job_id}").json()["plan"]
    plan["zooms"] = [{"start": 1, "end": 2}]
    monkeypatch.setattr(llm, "ask_json", lambda prompt, system="", **kw: {"message": "Zoom removed.", "ops": [{"op": "delete", "keys": ["z0"]}]})
    r = client.post(f"/jobs/{job_id}/assistant", json={"instruction": "remove the zoom", "plan": plan, "playhead": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["plan"]["zooms"] == [] and body["message"] == "Zoom removed." and body["changes"] == ["Removed z0"]
    assert client.get(f"/jobs/{job_id}").json()["plan"]["zooms"] == []  # the job's own plan never had it

    def down(prompt, system="", **kw):
        raise llm.LLMError("usage limit")

    monkeypatch.setattr(llm, "ask_json", down)
    r = client.post(f"/jobs/{job_id}/assistant", json={"instruction": "x", "plan": plan})
    assert r.status_code == 502 and "usage limit" in r.json()["detail"]


def test_import_job_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("HYPERCUT_MEDIA", str(tmp_path / "media"))
    from api import import_job, jobs
    from hypercut import plan as plan_mod

    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "normalized.mp4").write_bytes(b"video")
    plan_mod.save(EditPlan(source=SOURCE), folder / "plan_split.json")
    assert import_job.main([str(folder)]) == 1  # no plan.json
    job_id = import_job.import_job(folder, "plan_split.json")
    state = jobs.read(job_id)
    assert state["status"] == "done" and state["assets"] == []
    assert (jobs.job_dir(job_id) / "normalized.mp4").read_bytes() == b"video"
    assert plan_mod.load(jobs.job_dir(job_id) / "plan.json").source == SOURCE


def test_recut_rebuilds_segments_without_saving(client, fake_stages):
    from hypercut.plan import Segment, Transcript, Word

    job_id = _done_job(client, fake_stages)
    plan = client.get(f"/jobs/{job_id}").json()["plan"]
    words = [Word(start=1, end=2, text="One."), Word(start=4, end=5, text="Two.")]
    plan["transcript"] = Transcript(words=words).model_dump(mode="json")
    plan["hook"] = Hook().model_dump(mode="json")
    plan["segments"] = [Segment(start=0, end=10).model_dump(mode="json")]
    plan["style"]["pacing"]["keep_pause"] = 0.3
    r = client.post(f"/jobs/{job_id}/recut", json=plan)
    assert r.status_code == 200
    spans = [(s["start"], s["end"]) for s in r.json()["segments"]]
    assert spans[0][1] == 2.3 and spans[1][0] == 3.7  # the 2 s pause is cut, keeping 0.3 s each side
    assert client.get(f"/jobs/{job_id}").json()["plan"]["segments"] != r.json()["segments"]
    assert client.post("/jobs/000000000000/recut", json=plan).status_code == 404


def test_matte_endpoint_makes_the_cut_out_once(client, fake_stages, monkeypatch):
    made = []

    def matte(mp4, source, reframe, out):
        made.append(out)
        Path(out).write_bytes(b"webm")

    monkeypatch.setattr(run, "matte", matte)
    job_id = _submit(client)
    _wait(client, job_id)
    r = client.post(f"/jobs/{job_id}/matte")
    assert r.status_code == 202
    body = _wait(client, job_id, key="matte")
    assert body["matte"] == "done" and "matte.webm" in body["files"]
    assert client.post(f"/jobs/{job_id}/matte").json()["matte"] == "done" and len(made) == 1


def test_recipes_round_trip_and_start_a_job(client, fake_stages):
    from hypercut.plan import Style

    style = Style(name="mine").model_dump(mode="json")
    style["caption"]["color"] = "#FF0000"
    assert client.post("/recipes", json={"name": "Red captions", "style": style}).status_code == 201
    assert [r["name"] for r in client.get("/recipes").json()["recipes"]] == ["Red captions"]
    body = _wait(client, _submit(client, recipe="Red captions"))
    assert body["plan"]["style"]["caption"]["color"] == "#FF0000"  # used as is, not read from a prompt
    assert client.post("/jobs", files={"video": ("c.mp4", b"x")}, data={"recipe": "nope"}).status_code == 422
    assert client.delete("/recipes/Red captions").status_code == 200
    assert client.get("/recipes").json()["recipes"] == []


def test_generated_files_may_be_used_and_generate_endpoint(client, fake_stages, monkeypatch):
    from hypercut import generate

    job_id = _submit(client)
    plan = _wait(client, job_id)["plan"]
    assert client.get(f"/jobs/{job_id}").json()["generation"]["spent"] == 0
    plan["graphics"] = [{"id": "p1", "type": "media", "start": 0, "end": 1, "props": {"src": "gen-0123456789abcdef.jpg", "kind": "image"}}]
    assert client.put(f"/jobs/{job_id}/plan", json=plan).status_code == 422  # not fetched for this job
    from api import jobs

    (jobs.job_dir(job_id) / "gen-0123456789abcdef.jpg").write_bytes(b"jpg")
    assert client.put(f"/jobs/{job_id}/plan", json=plan).status_code == 200

    def fake_generate(p, job_dir, **kw):
        for g in p.graphics:
            g.props = {**g.props, "src": "gen-0123456789abcdef.jpg"}
        return p

    monkeypatch.setattr(generate, "generate", fake_generate)
    plan["graphics"][0]["props"] = {"generate": {"kind": "image", "prompt": "a"}, "title": "A"}
    r = client.post(f"/jobs/{job_id}/generate", json={"plan": plan, "graphic_id": "p1", "prompt": "b"})
    assert r.status_code == 200
    props = r.json()["plan"]["graphics"][0]["props"]
    assert props["src"] == "gen-0123456789abcdef.jpg" and props["generate"]["prompt"] == "b"
    assert client.post(f"/jobs/{job_id}/generate", json={"plan": plan, "graphic_id": "zz"}).status_code == 404


def test_variants_become_their_own_jobs(client, fake_stages):
    job_id = _submit(client)
    plan = _wait(client, job_id)["plan"]
    plan["segments"] = [{"start": 0, "end": 20, "reason": "body"}]
    r = client.post(f"/jobs/{job_id}/variants", json=plan)
    assert r.status_code == 201
    made = r.json()["variants"]
    assert made and made[0]["label"].startswith("Hook 2")
    other = client.get(f"/jobs/{made[0]['id']}").json()
    assert other["status"] == "done" and other["plan"]["hook"]["chosen"] == 1 and other["variant_of"] == job_id
    assert "normalized.mp4" in other["files"]


def test_review_needs_a_render(client, fake_stages):
    job_id = _submit(client)
    _wait(client, job_id)
    assert client.post(f"/jobs/{job_id}/review").status_code == 409


def test_pictures_are_off_unless_asked(client, fake_stages, monkeypatch):
    from hypercut import generate

    monkeypatch.setattr(generate, "available", lambda: set())
    assert client.get("/generation").json() == {"available": []}
    _wait(client, _submit(client))
    assert fake_stages["pictures"] is False
    _wait(client, _submit(client, pictures="true"))
    assert fake_stages["pictures"] is True


def test_history_undo_redo_name_and_restore(client, fake_stages):
    job_id = _done_job(client, fake_stages)
    h = client.get(f"/jobs/{job_id}/history").json()
    assert h["head"] == 1 and h["versions"][0]["kind"] == "pipeline" and not h["can_undo"]

    plan = client.get(f"/jobs/{job_id}").json()["plan"]
    plan["zooms"] = [{"start": 1, "end": 2}]
    client.put(f"/jobs/{job_id}/plan", json=plan, params={"kind": "assistant", "note": "zoom in at 1s"})
    h = client.get(f"/jobs/{job_id}/history").json()
    assert h["head"] == 2 and h["versions"][0]["note"] == "zoom in at 1s"
    assert h["versions"][0]["changes"] == ["Added a zoom at 0:01.0-0:02.0"]

    r = client.post(f"/jobs/{job_id}/history/undo").json()
    assert r["plan"]["zooms"] == [] and r["can_redo"] and client.get(f"/jobs/{job_id}").json()["plan"]["zooms"] == []
    assert client.post(f"/jobs/{job_id}/history/undo").status_code == 409
    assert client.post(f"/jobs/{job_id}/history/redo").json()["plan"]["zooms"] != []

    assert client.patch(f"/jobs/{job_id}/history/1", json={"label": "First cut"}).json()["label"] == "First cut"
    v = client.get(f"/jobs/{job_id}/history/1").json()
    assert v["changes_from_current"] == ["Removed a zoom at 0:01.0-0:02.0"]
    r = client.post(f"/jobs/{job_id}/history/1/restore").json()
    assert r["version"]["id"] == 3 and r["plan"]["zooms"] == []
    assert client.post(f"/jobs/{job_id}/history/9/restore").status_code == 404


def test_draft_autosave_and_explain(client, fake_stages):
    job_id = _done_job(client, fake_stages)
    plan = client.get(f"/jobs/{job_id}").json()["plan"]
    assert client.get(f"/jobs/{job_id}/draft").json() == {"draft": None}
    plan["style"]["caption"]["font"] = "Inter"
    assert client.put(f"/jobs/{job_id}/draft", json=plan).json()["base"] == 1
    d = client.get(f"/jobs/{job_id}/draft").json()["draft"]
    assert d["changes"] == ["Caption font: Montserrat → Inter"]
    client.delete(f"/jobs/{job_id}/draft")
    assert client.get(f"/jobs/{job_id}/draft").json() == {"draft": None}
    e = client.get(f"/jobs/{job_id}/explain").json()
    assert "summary" in e["first_cut"] and isinstance(e["current"]["items"], list)


def test_interrupted_work_is_marked_and_can_be_retried(client, fake_stages, monkeypatch):
    from api import jobs, main

    job_id = _done_job(client, fake_stages)
    jobs.write(job_id, status="running", stage="analyze", render="running")
    main.recover_interrupted()
    body = client.get(f"/jobs/{job_id}").json()
    assert body["status"] == "error" and body["interrupted"] and body["render"] == "error"
    assert "stopped" in body["render_error"]
    assert client.post(f"/jobs/{job_id}/retry").status_code == 202
    assert _wait(client, job_id)["status"] == "done"
    assert client.post(f"/jobs/{job_id}/retry").status_code == 409


def test_render_is_validated_and_plans_can_be_checked(client, fake_stages, monkeypatch):
    def render(job_dir):
        (Path(job_dir) / "output.mp4").write_bytes(b"not a video")
        return Path(job_dir) / "output.mp4"

    monkeypatch.setattr(run, "render_plan", render)
    job_id = _done_job(client, fake_stages)
    client.post(f"/jobs/{job_id}/render")
    for _ in range(100):
        body = client.get(f"/jobs/{job_id}").json()
        if isinstance(body.get("qa"), dict):
            break
        time.sleep(0.02)
    assert body["render"] == "done" and body["qa"]["ok"] is False  # the file does not open as a video
    assert "output.qa.json" in body["files"]

    plan = body["plan"]
    report = client.post(f"/jobs/{job_id}/checks", json=plan).json()
    assert report["ok"] and [i["code"] for i in report["issues"]] == ["ends_mid_sentence"]


def test_modes_listed_and_picked_at_upload(client, fake_stages):
    listed = client.get("/modes").json()
    assert listed["default"] == "talking_head" and {m["name"] for m in listed["modes"]} >= {"podcast", "vlog"}
    body = _wait(client, _submit(client, mode="product_demo"))
    assert body["mode"] == "product_demo" and body["plan"]["style"]["mode"] == "product_demo"
    assert client.post("/jobs", files={"video": ("c.mp4", b"x")}, data={"mode": "nope"}).status_code == 422


def test_job_shows_what_ingest_found(client, fake_stages):
    from api import jobs
    from hypercut.ingest import manifest

    job_id = _submit(client)
    _wait(client, job_id)
    assert client.get(f"/jobs/{job_id}").json()["manifest"] is None  # the fake ingest wrote none
    manifest.save(jobs.job_dir(job_id), {"video": {"orientation": "portrait"}, "warnings": ["The video is HDR"]})
    assert client.get(f"/jobs/{job_id}").json()["manifest"]["warnings"] == ["The video is HDR"]
