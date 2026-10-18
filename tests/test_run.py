import json
from pathlib import Path

import pytest

from hypercut import run
from hypercut.ingest import IngestError
from hypercut.plan import EditPlan, Reframe, ReframeKey, Source, Style, Transcript, Word

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

    def analyze(transcript, source, style, audio_wav=None, strategy="cold_open", visuals=False):
        seen["strategy"] = strategy
        seen["visuals"] = visuals
        return EditPlan(source=source, transcript=transcript, style=style)

    monkeypatch.setattr(run, "ingest", ingest)
    monkeypatch.setattr(run, "transcribe", transcribe)
    monkeypatch.setattr(run, "reframe", lambda mp4, source: Reframe(keys=[ReframeKey(t=0, cx=0.3, cy=0.5)]))
    monkeypatch.setattr(run, "style_from_prompt", style)
    monkeypatch.setattr(run, "analyze", analyze)
    return seen


def test_run_pipeline_writes_plan(tmp_path, stages):
    stage_names = []
    plan = run.run_pipeline("in.mp4", tmp_path / "job", "calm", "trim", on_stage=stage_names.append)
    assert stage_names == ["ingest", "transcribe", "style", "analyze"]
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
    run.run_pipeline("in.mp4", tmp_path / "b", "text behind me", on_stage=stage_names.append)
    assert made == [("matte.webm", 0.3)] and stage_names[-1] == "matte"


def test_failed_cut_out_still_saves_the_plan(tmp_path, stages, monkeypatch):
    def boom(*a):
        raise RuntimeError("no mediapipe")

    monkeypatch.setattr(run, "matte", boom)
    monkeypatch.setattr(run, "style_from_prompt", lambda prompt: Style(depth={"enabled": True}))
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
