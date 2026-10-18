import pytest

from hypercut import llm
from hypercut.plan import Style
from hypercut.style import PRESETS, get_preset, style_from_prompt


def fake(monkeypatch, *answers):
    calls = []
    queue = list(answers)

    def ask_json(prompt, system="", timeout=300):
        calls.append(prompt)
        a = queue.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    monkeypatch.setattr(llm, "ask_json", ask_json)
    return calls


def test_six_presets_valid():
    assert set(PRESETS) == {"bold_creator", "clean_corporate", "playful", "cinematic", "minimal", "podcast"}
    for name in PRESETS:
        s = get_preset(name)
        assert s.name == name
        assert Style.model_validate(s.model_dump()) == s


def test_get_preset_copy_and_unknown():
    get_preset("playful").caption.size = 1
    assert get_preset("playful").caption.size != 1
    with pytest.raises(KeyError):
        get_preset("nope")


@pytest.mark.parametrize("prompt", ["", "   "])
def test_empty_prompt_skips_claude(monkeypatch, prompt):
    calls = fake(monkeypatch)
    assert style_from_prompt(prompt) == get_preset("bold_creator")
    assert calls == []


def test_merge_changes(monkeypatch):
    fake(
        monkeypatch,
        {"preset": "cinematic", "changes": {"caption": {"color": "#FF0000"}, "camera": {"zoom_frequency": "high"}}},
    )
    s = style_from_prompt("moody but red")
    base = get_preset("cinematic")
    assert s.name == "cinematic"
    assert s.caption.color == "#FF0000"
    assert s.caption.font == base.caption.font  # untouched fields kept
    assert s.camera.zoom_frequency == "high"


def test_retry_then_success(monkeypatch):
    calls = fake(
        monkeypatch,
        {"preset": "playful", "changes": {"caption": {"size": "huge"}}},
        {"preset": "playful", "changes": {"caption": {"size": 90}}},
    )
    assert style_from_prompt("big").caption.size == 90
    assert len(calls) == 2


def test_fallback_to_chosen_preset(monkeypatch):
    bad = {"preset": "minimal", "changes": {"bogus": 1}}
    calls = fake(monkeypatch, bad, bad)
    assert style_from_prompt("x") == get_preset("minimal")
    assert len(calls) == 2


def test_fallback_to_default_on_errors(monkeypatch):
    fake(monkeypatch, llm.LLMError("no json"), {"preset": "unknown"})
    assert style_from_prompt("x") == get_preset("bold_creator")


def test_non_object_changes(monkeypatch):
    fake(monkeypatch, {"preset": "podcast", "changes": "none"}, {"preset": "podcast", "changes": []})
    assert style_from_prompt("x") == get_preset("podcast")


def test_green_screen_only_when_the_prompt_asks(monkeypatch):
    on = {"preset": "bold_creator", "changes": {"depth": {"enabled": True, "background": "blur"}}}
    fake(monkeypatch, on, on)
    asked = style_from_prompt("loud captions, put titles behind me and blur the background")
    assert asked.depth.enabled and asked.depth.background == "blur"
    # Claude turning it on for a prompt that never asked is overruled.
    assert not style_from_prompt("loud and energetic, yellow captions").depth.enabled
    assert not get_preset("cinematic").depth.enabled
