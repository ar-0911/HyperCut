import io
import json
import shutil
import subprocess

import pytest

from hypercut import edit, vision
from hypercut.plan import EditPlan, Graphic, LayoutSpan, Source, Transcript, Word
from hypercut.vision import Observation, Shot, VisualIndex, providers

SOURCE = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=30)
HAS_FFMPEG = shutil.which("ffmpeg") is not None


def _index():
    return VisualIndex(duration=30, shots=[
        Shot(id="shot_001", start=0, end=10, observations=[Observation(t=5, frame="a.jpg", description="a woman talking", scene_type="talking_head", confidence=0.9)]),
        Shot(id="shot_002", start=10, end=18, observations=[Observation(t=14, frame="b.jpg", description="a dashboard showing revenue", scene_type="screen",
                                                                        visible_text=["Revenue", "Dashboard"], objects=["laptop"], confidence=0.8)]),
        Shot(id="shot_003", start=18, end=30),
    ])


def test_shots_and_frame_sampling():
    assert vision.shots_from_cuts([0.2, 5, 5.3, 12], 20) == [(0.0, 5.3), (5.3, 12), (12, 20)]
    picks = vision.sample_times([(0, 4), (4, 30)], cap=4)
    assert picks[0] == (0, 2.0) and len(picks) == 4 and all(i == 1 for i, _ in picks[1:])
    assert len(vision.sample_times([(i, i + 1) for i in range(50)], cap=24)) == 24


def test_summary_and_scene_types():
    idx = _index()
    assert idx.shots[2].scene_type == "unknown" and idx.at(12).id == "shot_002"
    lines = vision.summary(idx).splitlines()
    assert lines[1] == "10.0-18.0: screen; a dashboard showing revenue; text: Revenue | Dashboard; objects: laptop"


def test_keep_footage_clears_visuals_off_a_shot_that_shows_it():
    plan = EditPlan(source=SOURCE, layout=[LayoutSpan(start=9, end=17, mode="split")], graphics=[
        Graphic(id="v1", type="illustration", start=11, end=16, props={"title": "Revenue"}),
        Graphic(id="g1", type="lower_third", start=11, end=13, props={"title": "Ann"}),
        Graphic(id="v2", type="illustration", start=2, end=6, props={"title": "Intro"}),
    ])
    changes = vision.keep_footage(plan, _index())
    assert [g.id for g in plan.graphics] == ["g1", "v2"]
    assert changes == ["Kept the footage at 10.0-18.0 s instead of v1: it shows a dashboard showing revenue"]
    assert [(s.start, s.end, s.mode) for s in plan.layout] == [(9, 10, "split")]


def test_fix_words_respells_names_from_the_screen():
    idx = _index()
    idx.shots[0].observations[0].visible_text = ["KACHAVA", "the best shake"]
    t = Transcript(words=[Word(text="love", start=0, end=1), Word(text="Kachaba.", start=1, end=2), Word(text="shape", start=2, end=3),
                          Word(text="kachaba", start=3, end=4)])
    fixed = vision.fix_words(t, idx)  # a name (capitalized mid-sentence) close to the screen's spelling; "shape" is no name
    assert [w.text for w in t.words] == ["love", "Kachava.", "shape", "kachava"]
    assert [(c.heard, c.written) for c in fixed] == [("Kachaba", "Kachava"), ("kachaba", "kachava")]


def test_claude_provider_batches_and_cleans(monkeypatch, tmp_path):
    frames = [tmp_path / f"{i}.jpg" for i in range(10)]
    calls = []

    def ask(prompt, images=None, **kw):
        calls.append(len(images))
        return {"frames": [{"frame": 0, "description": "a laptop", "scene_type": "screen", "visible_text": ["Login"], "objects": ["laptop"], "people": 0, "confidence": 2},
                           {"frame": 1, "scene_type": "spaceship"}, "junk"]}

    monkeypatch.setattr(providers.llm, "ask_json", ask)
    out = providers.get("claude").describe(frames, [float(i) for i in range(10)])
    assert calls == [8, 2]
    assert out[0]["scene_type"] == "screen" and out[0]["confidence"] == 1.0 and out[1]["scene_type"] == "unknown"
    assert out[2] is None and out[8]["description"] == "a laptop"
    assert providers.get("none").describe(frames, [0.0] * 10) == [None] * 10


def test_ollama_provider_and_a_model_that_is_not_running(tmp_path):
    frame = tmp_path / "f.jpg"
    frame.write_bytes(b"jpg")
    sent = {}

    class Res(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout):
        sent.update(json.loads(req.data))
        return Res(json.dumps({"response": json.dumps({"description": "a mug", "scene_type": "product", "objects": ["mug"], "confidence": 0.7})}).encode())

    out = providers.Ollama(model="m", opener=opener).describe([frame], [3.0])
    assert out[0]["scene_type"] == "product" and sent["model"] == "m" and sent["images"]

    def down(req, timeout):
        raise OSError("connection refused")

    assert providers.Ollama(opener=down).describe([frame], [3.0]) == [None]


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs FFmpeg")
def test_build_index_from_a_real_video(tmp_path):
    mp4 = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=red:size=320x240:rate=30:duration=3",
                    "-f", "lavfi", "-i", "color=blue:size=320x240:rate=30:duration=3", "-filter_complex", "[0:v][1:v]concat=n=2:v=1",
                    "-pix_fmt", "yuv420p", str(mp4)], check=True)
    src = Source(path=str(mp4), width=320, height=240, fps=30, duration=6)
    idx = vision.build_index(mp4, src, None, tmp_path)
    assert len(idx.shots) == 2 and abs(idx.shots[0].end - 3) < 0.1  # the hard cut found by FFmpeg
    assert all(len(s.observations) == 1 for s in idx.shots) and (tmp_path / "frames" / idx.shots[0].observations[0].frame).is_file()
    assert vision.load(tmp_path / "visual_index.json") == idx


def test_first_cut_explains_spelling_and_kept_footage():
    from hypercut import explain
    from hypercut.vision import Correction

    idx = _index()
    idx.corrections = [Correction(t=3, heard="Kachaba", written="Kachava")]
    plan = EditPlan(source=SOURCE, transcript=Transcript(words=[Word(text="Kachava", start=3, end=3.5)]))
    texts = [i["text"] for i in explain.first_cut(plan, idx)["items"]]
    assert "Spelled “Kachaba” as “Kachava”, the way it is written in the footage." in texts
    assert "Kept the footage clear of graphics: it shows a dashboard showing revenue." in texts
