import importlib

from hypercut import assistant, diff, modes
from hypercut.plan import EditPlan, Segment, Source, Style, Transcript, Word
from hypercut.style import get_preset

analyze_mod = importlib.import_module("hypercut.analyze.analyze")


def test_every_mode_makes_a_valid_style():
    for name in modes.MODES:
        style = modes.apply(get_preset("bold_creator"), name)
        assert style.mode == name
    assert modes.apply(Style(), "podcast").pacing.max_silence == 0.3
    assert modes.get("nonsense").name == modes.DEFAULT_MODE


def test_what_the_user_asked_for_wins_over_the_mode():
    style = get_preset("bold_creator")
    style.caption.font = "Bebas Neue"  # from the style prompt
    demo = modes.apply(style, "product_demo")
    assert demo.caption.font == "Bebas Neue" and demo.transitions.style == "hard" and demo.caption.box


def test_switching_mode_leaves_nothing_of_the_old_one():
    demo = modes.apply(get_preset("bold_creator"), "product_demo")
    vlog = modes.apply(demo, "vlog")
    assert vlog.caption.box is None and vlog.transitions.style == "smooth"
    assert modes.apply(demo, "talking_head") == get_preset("bold_creator")


def test_guidance_reaches_the_planner(monkeypatch):
    asked = {}

    def ask(prompt, system=None, **kw):
        asked["prompt"] = prompt
        return {}

    monkeypatch.setattr(analyze_mod.llm, "ask_json", ask)
    source = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=4)
    transcript = Transcript(words=[Word(text="hi", start=0, end=1)])
    analyze_mod.analyze(transcript, source, modes.apply(Style(), "product_demo"))
    assert "PRODUCT DEMO" in asked["prompt"]
    analyze_mod.analyze(transcript, source, Style())
    assert "Editing mode" not in asked["prompt"]


def test_assistant_mode_op_recuts_and_is_explained():
    words = [Word(text=f"w{i}", start=i * 1.0, end=i * 1.0 + 0.5) for i in range(10)]
    plan = EditPlan(source=Source(path="n.mp4", width=1920, height=1080, fps=30, duration=10),
                    transcript=Transcript(words=words), segments=[Segment(start=0, end=10)])
    new, changes = assistant.apply_ops(plan, [{"op": "mode", "mode": "podcast"}], playhead=0, assets=[])
    assert new.style.mode == "podcast" and any("podcast clip" in c for c in changes)
    assert any("Re-cut" in c for c in changes)
    assert "Editing mode: Talking head → Podcast clip" in diff.explain(plan, new)
    same, changes = assistant.apply_ops(new, [{"op": "mode", "mode": "podcast"}], playhead=0, assets=[])
    assert changes == []
