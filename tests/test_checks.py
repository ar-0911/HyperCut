import json
import shutil
import subprocess
from pathlib import Path

import pytest

from hypercut import bench, checks, history, qa
from hypercut import plan as plan_mod
from hypercut.plan import EditPlan, Graphic, Hook, HookCandidate, Segment, Source, Transcript, Word

SOURCE = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=40)
FIXTURES = Path(__file__).parent / "fixtures"
HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _words(n=30):
    return [Word(text=f"w{i}." if i % 5 == 4 else f"w{i}", start=i, end=i + 0.8) for i in range(n)]


def _codes(plan, job_dir=None):
    return [i.code for i in checks.check(plan, job_dir)]


def test_clean_plan_has_no_issues():
    plan = EditPlan(source=SOURCE, transcript=Transcript(words=_words(20)), segments=[Segment(start=0, end=19.9)])
    assert _codes(plan) == []


def test_finds_clipped_words_pauses_ending_and_length():
    words = _words(12) + [Word(text="later", start=13, end=13.5)]
    plan = EditPlan(source=SOURCE, transcript=Transcript(words=words), segments=[Segment(start=0, end=3.5), Segment(start=4, end=13.6)])
    issues = checks.check(plan)
    codes = [i.code for i in issues]
    assert codes[0] == "word_clipped" and issues[0].severity == "fail"  # w3 runs 3.0-3.8, cut at 3.5
    assert "long_pause" in codes  # 11.8 -> 13.0 is still in
    assert "ends_mid_sentence" in codes and "too_short" in codes
    assert not checks.report(plan)["ok"]


def test_hook_visuals_and_missing_files(tmp_path):
    words = _words(30)
    plan = EditPlan(
        source=SOURCE, transcript=Transcript(words=words),
        hook=Hook(candidates=[HookCandidate(start=7, end=9.9, text="w7 w8 w9.", score=0.9)]),
        segments=[Segment(start=7, end=9.9, reason="hook"), Segment(start=0, end=29.9)],
        graphics=[
            Graphic(id="v1", type="illustration", start=10, end=14, props={"title": "Rocket"}),
            Graphic(id="v2", type="illustration", start=12, end=16, props={"title": "Rocket"}),
            Graphic(id="g1", type="kinetic_text", start=20, end=20.3, props={"text": "HI"}),
            Graphic(id="m1", type="media", start=22, end=24, props={"src": "asset-000000000000.jpg"}),
        ],
    )
    codes = _codes(plan, tmp_path)
    assert codes[0] == "missing_file"
    for c in ("hook_mid_sentence", "visuals_overlap", "visual_repeated", "graphic_flash"):
        assert c in codes
    (tmp_path / "asset-000000000000.jpg").write_bytes(b"x")
    assert "missing_file" not in _codes(plan, tmp_path)


def test_regression_real_footage_plan_has_no_defects():
    """The plan HyperCut made for the 69 s real test footage: a change that clips words, breaks the hook or
    the visuals there shows up here."""
    plan = plan_mod.load(FIXTURES / "real_footage_plan.json")
    report = checks.report(plan)
    assert report["ok"], report
    assert {i["code"] for i in report["issues"]} <= {"hook_mid_sentence"}  # known: the hook starts after "and"
    s = bench.score(plan, {"hook": "Kachaba makes my life so much easier"})
    assert s["hook_match"] == 1.0 and s["fails"] == 0 and 45 <= s["reel_seconds"] <= 60


def test_wer_overlap_and_compare():
    assert bench.wer("the cat sat", "the cat sat") == 0
    assert bench.wer("the cat sat", "a cat sat down") == pytest.approx(2 / 3)
    assert bench.overlap("Hello world", "hello there world") == pytest.approx(2 / 3)
    old = {"results": [{"video": "a.mp4", "scores": {"fails": 0, "issues": {}, "wer": 0.05, "hook_match": 0.9}, "qa": {"ok": True}}]}
    new = {"results": [{"video": "a.mp4", "scores": {"fails": 1, "issues": {"word_clipped": 1}, "wer": 0.1, "hook_match": 0.5}, "qa": {"ok": False}}]}
    regs = bench.compare(old, new)
    assert len(regs) == 4 and "word_clipped" in regs[0]
    assert bench.compare(old, old) == []


def test_benchmark_runs_each_video_and_survives_errors(tmp_path):
    bench_dir = tmp_path / "bench"
    bench_dir.mkdir()
    (bench_dir / "good.mp4").write_bytes(b"v")
    (bench_dir / "good.json").write_text(json.dumps({"style": "calm", "transcript": "w0 w1 w2", "hook": "w0"}))
    (bench_dir / "bad.mp4").write_bytes(b"v")

    def pipeline(video, out_dir, style, on_stage):
        if video.name == "bad.mp4":
            raise ValueError("no audio")
        on_stage("transcribe")
        assert style == "calm"
        return EditPlan(source=SOURCE, transcript=Transcript(words=_words(25)), segments=[Segment(start=0, end=24.9)],
                        hook=Hook(candidates=[HookCandidate(start=0, end=1, text="w0", score=1)]))

    report = bench.benchmark(bench_dir, tmp_path / "out", pipeline=pipeline)
    bad, good = report["results"]
    assert bad["error"] == "no audio"
    assert good["scores"]["hook_match"] == 1.0 and good["scores"]["wer"] > 0.8  # reference has 3 of 25 words
    assert (tmp_path / "out" / "report.md").read_text().count("|") > 10


def test_correction_effort_from_history(tmp_path):
    plan = EditPlan(source=SOURCE, transcript=Transcript(words=_words(5)))
    history.commit(tmp_path / "j1", plan, "pipeline", changes=[])
    edited = plan.model_copy(deep=True)
    edited.style.caption.font = "Inter"
    history.commit(tmp_path / "j1", edited, "assistant")
    history.commit(tmp_path / "j2", plan, "pipeline", changes=[])
    summary = bench.corrections(tmp_path)
    assert summary["projects"] == 2 and summary["kept_as_is"] == 1 and summary["mean_changes"] == 1
    assert summary["jobs"][0]["assistant_edits"] == 1


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs FFmpeg")
def test_export_validation_on_real_files(tmp_path):
    good, black = tmp_path / "good.mp4", tmp_path / "black.mp4"
    base = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=4",
            "-f", "lavfi", "-i", "sine=frequency=300:duration=4", "-shortest", "-pix_fmt", "yuv420p"]
    subprocess.run(base + [str(good)], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=black:size=720x1280:rate=25:duration=4",
                    "-pix_fmt", "yuv420p", str(black)], check=True)
    plan = EditPlan(source=SOURCE, segments=[Segment(start=0, end=4)])
    plan.style.transitions.fade_out = 0
    result = qa.validate(plan, good)
    status = {c["name"]: c["status"] for c in result["checks"]}
    assert result["ok"] and status["size"] == status["duration"] == status["av_sync"] == status["black_frames"] == "pass"
    result = qa.validate(plan, black)
    status = {c["name"]: c["status"] for c in result["checks"]}
    assert not result["ok"]
    assert status["audio"] == status["size"] == status["frame_rate"] == status["black_frames"] == "fail"
    assert qa.validate(plan, tmp_path / "missing.mp4")["checks"][0]["status"] == "fail"
