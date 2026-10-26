import json
from pathlib import Path

import pytest

from hypercut import run
from hypercut.ingest import IngestError
from hypercut.plan import EditPlan, Reframe, ReframeKey, Source, Style, Transcript, Word
from hypercut.vision import Observation, Shot, VisualIndex

SOURCE = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=20)


@pytest.fixture
def stages(monkeypatch):
    seen = {"order": []}

    def ingest(video, job_dir):
        seen["order"].append("ingest")
        Path(job_dir).mkdir(parents=True, exist_ok=True)
        return SOURCE, Path(job_dir) / "normalized.mp4", Path(job_dir) / "audio.wav"

    def transcribe(wav):
        seen["order"].append("transcribe")
        return Transcript(words=[Word(text="hi", start=0, end=1)])

    def style(prompt):
        seen["style"] = prompt
        return Style()

    def analyze(transcript, source, style, audio_wav=None, strategy="cold_open", visuals=False, pictures=False):
        seen["strategy"] = strategy
        seen["visuals"] = visuals
        return EditPlan(source=source, transcript=transcript, style=style)

    monkeypatch.setattr(run, "ingest", ingest)
    monkeypatch.setattr(run, "transcribe", transcribe)
    monkeypatch.setattr(run, "reframe", lambda mp4, source: Reframe(keys=[ReframeKey(t=0, cx=0.3, cy=0.5)]))
    monkeypatch.setattr(run, "style_from_prompt", style)
    monkeypatch.setattr(run, "analyze", analyze)
    monkeypatch.setattr(run, "build_index", lambda mp4, source, reframe, job_dir, provider: VisualIndex(duration=source.duration))
    return seen


def test_run_pipeline_writes_plan(tmp_path, stages):
    stage_names = []
    plan = run.run_pipeline("in.mp4", tmp_path / "job", "calm", "trim", on_stage=stage_names.append)
    assert stage_names == ["ingest", "transcribe", "style", "look", "analyze"]
    assert stages["style"] == "calm" and stages["strategy"] == "trim" and stages["visuals"] is True
    saved = json.loads((tmp_path / "job" / "plan.json").read_text())
    assert saved["reframe"]["keys"][0]["cx"] == 0.3 and plan.reframe.keys


def test_cli_success(tmp_path, stages, capsys):
    out = tmp_path / "o"
    assert run.main(["in.mp4", "--style", "loud", "--out", str(out)]) == 0
    assert (out / "plan.json").is_file()
    assert "1 words" in capsys.readouterr().out


def test_cli_reports_stage_error(tmp_path, stages, monkeypatch, capsys):
    def bad(video, job_dir):
        raise IngestError("no audio track")

    monkeypatch.setattr(run, "ingest", bad)
    assert run.main(["in.mp4", "--out", str(tmp_path)]) == 1
    assert "no audio track" in capsys.readouterr().err


def test_cut_out_only_when_the_style_asks(tmp_path, stages, monkeypatch):
    made = []
    monkeypatch.setattr(run, "matte", lambda mp4, source, reframe, out: made.append((Path(out).name, reframe.keys[0].cx)))
    stage_names = []
    run.run_pipeline("in.mp4", tmp_path / "a", "calm", on_stage=stage_names.append)
    assert made == [] and "matte" not in stage_names

    monkeypatch.setattr(run, "style_from_prompt", lambda prompt: Style(depth={"enabled": True}))
    run.run_pipeline("in.mp4", tmp_path / "e", "particles around me", on_stage=stage_names.append)
    assert made == [] and "matte" not in stage_names  # effects over the real footage: no cut-out

    monkeypatch.setattr(run, "style_from_prompt", lambda prompt: Style(depth={"enabled": True, "cutout": True}))
    run.run_pipeline("in.mp4", tmp_path / "b", "text behind me", on_stage=stage_names.append)
    assert made == [("matte.webm", 0.3)] and stage_names[-1] == "matte"


def test_failed_cut_out_still_saves_the_plan(tmp_path, stages, monkeypatch):
    def boom(*a):
        raise RuntimeError("no mediapipe")

    monkeypatch.setattr(run, "matte", boom)
    monkeypatch.setattr(run, "style_from_prompt", lambda prompt: Style(depth={"enabled": True, "cutout": True}))
    run.run_pipeline("in.mp4", tmp_path / "c", "green screen")
    assert (tmp_path / "c" / "plan.json").is_file()


def test_ensure_matte(tmp_path, monkeypatch):
    made = []
    monkeypatch.setattr(run, "matte", lambda mp4, source, reframe, out: made.append(out) or Path(out).write_bytes(b"x"))
    job = tmp_path / "j"
    job.mkdir()
    (job / "plan.json").write_text(EditPlan(source=SOURCE).model_dump_json())
    assert run.ensure_matte(job) is None and made == []
    assert run.ensure_matte(job, force=True) == job / "matte.webm" and len(made) == 1
    run.ensure_matte(job, force=True)
    assert len(made) == 1  # made once


def test_items_added_in_the_editor_are_drawn_before_render(tmp_path):
    from hypercut import plan as plan_mod
    from hypercut.plan import Graphic

    job = tmp_path / "j"
    job.mkdir()
    orbit = Graphic(id="u1", type="orbit", start=0, end=3, props={"items": ["rocket"]})
    plan = EditPlan(source=SOURCE, graphics=[orbit])
    (job / "plan.json").write_text(plan.model_dump_json())
    draw = lambda names, accent: [{"viewBox": "0 0 400 400", "body": "<g/>"} for _ in names]  # noqa: E731
    run.draw_new_around(job, draw)
    assert "art" not in plan_mod.load(job / "plan.json").graphics[0].props  # effects off: nothing drawn
    plan.style.depth.enabled = True
    (job / "plan.json").write_text(plan.model_dump_json())
    run.draw_new_around(job, draw)
    assert plan_mod.load(job / "plan.json").graphics[0].props["art"]["rocket"]["body"] == "<g/>"
    plan.graphics = [Graphic(id="u2", type="scene", start=0, end=3, props={"brief": "a beach"})]
    (job / "plan.json").write_text(plan.model_dump_json())
    art = {"viewBox": "0 0 1080 1920", "defs": "", "layers": ["<g/>"]}
    run.draw_new_around(job, draw, illustrate=lambda briefs, *a: [art for _ in briefs])
    assert plan_mod.load(job / "plan.json").graphics[0].props["layers"] == ["<g/>"]


def test_visual_index_reaches_the_planner_and_fixes_names(tmp_path, stages, monkeypatch):
    seen = {}
    shot = Shot(id="shot_001", start=0, end=20, observations=[
        Observation(t=10, frame="f.jpg", description="a bottle on a table", scene_type="product", visible_text=["KACHAVA shake"], confidence=0.9)])
    monkeypatch.setattr(run, "build_index", lambda mp4, source, reframe, job_dir, provider: seen.setdefault("provider", provider) and VisualIndex(duration=20, shots=[shot]))
    monkeypatch.setattr(run, "transcribe", lambda wav: Transcript(words=[Word(text="and", start=0, end=0.5), Word(text="Kachaba,", start=0.5, end=1)]))

    def analyze(transcript, source, style, audio_wav=None, strategy="cold_open", visuals=False, pictures=False, visual_index=None):
        seen["index"] = visual_index
        return EditPlan(source=source, transcript=transcript, style=style)

    monkeypatch.setattr(run, "analyze", analyze)
    plan = run.run_pipeline("in.mp4", tmp_path / "job", vision="claude")
    assert seen["provider"] == "claude" and seen["index"].shots[0].scene_type == "product"
    assert plan.transcript.words[1].text == "Kachava,"
    saved = json.loads((tmp_path / "job" / "visual_index.json").read_text())
    assert saved["corrections"] == [{"t": 0.5, "heard": "Kachaba", "written": "Kachava"}]


def test_mode_sets_how_the_reel_is_edited(tmp_path, stages):
    plan = run.run_pipeline("in.mp4", tmp_path / "job", "", mode="vlog")
    assert plan.style.mode == "vlog" and plan.style.transitions.style == "smooth"
    assert run.run_pipeline("in.mp4", tmp_path / "j2", "").style.mode == "talking_head"
