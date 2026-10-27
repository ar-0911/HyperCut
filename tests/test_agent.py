import subprocess
from pathlib import Path

import pytest

from hypercut import agent, edit, llm
from hypercut.plan import EditPlan, Graphic, Hook, HookCandidate, Segment, Source, Transcript, Word

SOURCE = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=200)


def _talk(seconds, sentence=8):
    """A word every 0.5 s, a sentence every `sentence` words."""
    words = []
    for i in range(int(seconds * 2)):
        end = (i + 1) % sentence == 0
        words.append(Word(text=f"w{i}{'.' if end else ''}", start=i * 0.5, end=i * 0.5 + 0.4))
    return Transcript(words=words)


def test_claude_clips_are_checked():
    tr = _talk(200)  # sentences of 4 s: sentence k spans 4k .. 4k+3.9
    answer = {"clips": [
        {"first": 0, "last": 9, "title": "Good one", "why": "strong"},     # 0-39.9 s
        {"first": 5, "last": 14, "title": "Overlaps", "why": ""},          # overlaps the first
        {"first": 20, "last": 21, "title": "Too short", "why": ""},        # 8 s
        {"first": 30, "last": 99, "title": "Out of range", "why": ""},
        {"first": 20, "last": 31, "title": "Second", "why": "ok"},         # 80-127.9 s
    ]}
    clips = agent.propose(tr, 200, 4, ask=lambda prompt, system="": answer)
    assert [c.title for c in clips] == ["Good one", "Second"]
    assert clips[0].start == 0 and clips[0].end == pytest.approx(39.9)


def test_without_claude_code_picks_clips_across_the_recording():
    def down(prompt, system=""):
        raise llm.LLMError("no CLI")

    clips = agent.plan_clips(_talk(200), 200, 3, ask=down)
    assert len(clips) == 3 and all(c.picked_by == "code" for c in clips)
    assert all(agent.MIN_CLIP <= c.end - c.start <= agent.MAX_CLIP for c in clips)
    assert all(a.end <= b.start for a, b in zip(clips, clips[1:]))
    assert clips[-1].start > 100  # spread out, not all at the start


def test_excerpt_words_are_on_the_excerpt_timeline():
    words = agent.excerpt_words(_talk(100), 40.0, 60.0)
    assert words.words[0].start == pytest.approx(agent.EXCERPT_PAD)
    assert all(w.end <= 20 + agent.EXCERPT_PAD + 0.01 for w in words.words)


def _plan(seconds, **kw):
    tr = _talk(seconds)
    end = tr.words[-1].end
    return EditPlan(source=SOURCE.model_copy(update={"duration": end + 1}), transcript=tr,
                    segments=[Segment(start=0, end=end, reason="body")], **kw)


def test_self_check_fixes_what_code_can():
    plan = _plan(80, graphics=[Graphic(id="g1", type="kinetic_text", start=79.5, end=80.5, props={"text": "x"})])
    plan.segments = [Segment(start=0, end=75, reason="body")]  # the graphic sits in cut footage
    fixed, fixes, left = agent.self_check(plan)
    assert edit.reel_duration(fixed) <= agent.MAX_REEL + 0.5
    assert not fixed.graphics
    assert len(fixes) == 2 and not left


def test_run_agent_plans_then_makes_each_reel(tmp_path, monkeypatch):
    from hypercut import ingest as ingest_mod
    from hypercut import transcribe as transcribe_mod

    long = tmp_path / "long.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=120",
                    "-f", "lavfi", "-i", "sine=duration=120", "-c:v", "libx264", "-c:a", "aac", str(long)], check=True)

    def ingest(video, job_dir, max_seconds=180):
        assert max_seconds > 180  # a long recording is allowed here
        return SOURCE.model_copy(update={"duration": 120}), Path(video), Path(job_dir) / "audio.wav"

    monkeypatch.setattr(ingest_mod, "ingest", ingest)
    monkeypatch.setattr(transcribe_mod, "transcribe", lambda wav: _talk(120))
    made = []

    def make(video, job_dir, style, strategy, mode=None, kit=None, transcript=None):
        made.append((Path(video).name, transcript.words[0].start))
        if len(made) == 2:
            raise RuntimeError("render engine on fire")
        plan = _plan(30)
        plan.hook = Hook(candidates=[HookCandidate(start=0, end=2, text="w0", score=0.9)])
        return plan

    answer = {"clips": [{"first": 0, "last": 7, "title": "One"}, {"first": 10, "last": 17, "title": "Two"},
                        {"first": 20, "last": 27, "title": "Three"}]}
    seen = []
    state = agent.run_agent(long, tmp_path / "session", count=3, ask=lambda p, system="": answer, make=make,
                            on_update=lambda s: seen.append((s["step"], len(s["clips"]))))
    assert ("make", 3) in seen and seen.index(("plan", 0)) < seen.index(("make", 3))  # planned before acting
    assert [c["status"] for c in state["clips"]] == ["done", "failed", "done"]
    assert state["status"] == "done" and "on fire" in state["clips"][1]["error"]
    assert made[0] == ("upload.mp4", 0.0) and made[1][1] == pytest.approx(agent.EXCERPT_PAD)
    assert (tmp_path / "session" / "reel-1" / "upload.mp4").is_file()
    assert agent.load(tmp_path / "session")["clips"][0]["title"] == "One"
