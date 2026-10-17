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

    def analyze(transcript, source, style, audio_wav=None, strategy="cold_open"):
        seen["strategy"] = strategy
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
    assert stages["style"] == "calm" and stages["strategy"] == "trim"
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
