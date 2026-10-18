from pathlib import Path

import pytest

from hypercut import llm, plan
from hypercut.analyze import analyze
from hypercut.analyze import cuts
from hypercut.plan import Style, Transcript, Word

SAMPLE = Path(__file__).resolve().parent.parent / "schema" / "examples" / "sample_plan.json"


@pytest.fixture
def sample():
    return plan.load(SAMPLE)


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []

    def install(answer):
        def ask_json(prompt, system="", timeout=300):
            calls.append(prompt)
            return answer

        monkeypatch.setattr(llm, "ask_json", ask_json)
        return calls

    return install


GOOD = {
    "hooks": [
        {"start_word": 7, "end_word": 11, "score": 0.6, "why": "payoff tease"},
        {"start_word": 0, "end_word": 6, "score": 0.9, "why": "surprising number"},
    ],
    "graphics": [{"type": "stat_card", "start": 1.1, "end": 2.2, "props": {"value": "10"}}],
    "zooms": [{"start": 6.0, "end": 7.3, "ease": "snap"}],
}


def run(sample, **kw):
    return analyze(sample.transcript, sample.source, kw.pop("style", Style()), **kw)


def test_cold_open_puts_hook_first_and_keeps_it_in_place(sample, fake_llm):
    calls = fake_llm(GOOD)
    p = run(sample)
    assert len(calls) == 1
    assert [c.score for c in p.hook.candidates] == [0.9, 0.6]
    assert p.hook.chosen == 0
    assert p.hook.candidates[0].text == "Most people waste ten hours a week."
    assert p.segments[0].reason == "hook"
    assert (p.segments[0].start, p.segments[0].end) == (0.2, 2.2)
    bodies = [s for s in p.segments if s.reason == "body"]
    assert bodies[0].start < 0.3 and bodies[0].end > 2.0  # hook words also in original place
    assert p.graphics[0].id == "g1" and p.zooms[0].ease == "snap"
    plan.EditPlan.model_validate(p.model_dump())


def test_gap_longer_than_max_silence_is_cut(sample, fake_llm):
    fake_llm(GOOD)
    p = run(sample)
    bodies = [s for s in p.segments if s.reason == "body"]
    # 2.2s -> 6.0s is dead air: nothing kept in the middle of it
    assert all(not (s.start < 5.0 and s.end > 3.0) for s in bodies)
    assert bodies[-1].end < 7.5  # trailing silence after last word dropped


def test_trim_drops_everything_before_hook(sample, fake_llm):
    fake_llm({**GOOD, "hooks": [{"start_word": 7, "end_word": 11, "score": 0.9}]})
    p = run(sample, strategy="trim")
    assert p.hook.strategy == "trim"
    assert all(s.reason == "body" for s in p.segments)
    assert p.segments[0].start == pytest.approx(6.0)


def test_fillers_are_cut(fake_llm):
    words = [
        Word(text="So", start=0.0, end=0.3),
        Word(text="um,", start=0.3, end=0.7),
        Word(text="this", start=0.7, end=1.0),
        Word(text="works.", start=1.0, end=1.5),
    ]
    fake_llm({"hooks": [], "graphics": [], "zooms": []})
    src = plan.Source(path="x.mp4", width=10, height=10, fps=30, duration=1.5)
    p = analyze(Transcript(words=words), src, Style())
    assert [(s.start, s.end) for s in p.segments] == [(0.0, 0.3), (0.7, 1.5)]
    p = analyze(Transcript(words=words), src, Style(pacing=plan.Pacing(remove_fillers=False)))
    assert [(s.start, s.end) for s in p.segments] == [(0.0, 1.5)]


def test_invalid_claude_items_are_dropped(sample, fake_llm):
    fake_llm({
        "hooks": [
            {"start_word": 0, "end_word": 99, "score": 0.5},
            {"start_word": 5, "end_word": 2, "score": 0.5},
            "nonsense",
            {"start_word": 0, "end_word": 6, "score": 7},
        ],
        "graphics": [
            {"type": "hologram", "start": 1, "end": 2},
            {"type": "kinetic_text", "start": 11, "end": 20},
            {"type": "kinetic_text", "start": "a", "end": 2},
            {"type": "emoji_burst", "start": 3, "end": 3.1},
            {"type": "kinetic_text", "start": 1, "end": 2, "props": "bad"},
        ],
        "zooms": [{"start": -1, "end": 2}, {"start": 5, "end": 99}, None, {"start": 1, "end": 2, "ease": "wobble"}],
    })
    p = run(sample)
    assert len(p.hook.candidates) == 1 and p.hook.candidates[0].score == 1.0
    assert [(g.type, g.props) for g in p.graphics] == [("kinetic_text", {})]
    assert [(z.start, z.ease) for z in p.zooms] == [(1.0, "ease_in_out")]


def test_density_and_zoom_frequency_cap_counts(sample, fake_llm):
    many = [{"type": "emoji_burst", "start": float(i), "end": i + 0.5} for i in range(10)]
    zooms = [{"start": float(i), "end": i + 0.5} for i in range(10)]
    fake_llm({"hooks": [], "graphics": many, "zooms": zooms})
    style = Style(
        graphics=plan.GraphicsStyle(density="minimal"),
        camera=plan.Camera(zoom_frequency="low", zoom_scale=1.3),
    )
    p = run(sample, style=style)  # 12 s of video
    assert len(p.graphics) == 1 and len(p.zooms) == 1
    assert p.zooms[0].scale == 1.3
    p = run(sample, style=Style(camera=plan.Camera(zoom_frequency="none")))
    assert p.zooms == []


def test_no_hook_still_produces_segments(sample, fake_llm):
    fake_llm({})
    p = run(sample)
    assert p.hook.candidates == []
    assert p.segments and all(s.reason == "body" for s in p.segments)


def test_empty_transcript_skips_claude(sample, fake_llm):
    calls = fake_llm(GOOD)
    p = analyze(Transcript(), sample.source, Style())
    assert calls == [] and p.segments == []


def test_unknown_strategy(sample):
    with pytest.raises(ValueError):
        run(sample, strategy="loop")


def test_silencedetect_cuts_extra_silence(sample, monkeypatch, fake_llm):
    fake_llm({})
    monkeypatch.setattr(cuts, "detect_silences", lambda wav, d: [(0.9, 1.5)])
    p = run(sample, audio_wav="x.wav")
    assert any(abs(s.end - 1.05) < 1e-6 for s in p.segments)  # 0.9 + the default 0.15 s kept pause


def test_cut_helpers():
    assert cuts.is_filler("Um,") and not cuts.is_filler("umbrella")
    assert cuts.subtract((0, 10), [(2, 3), (3, 5)]) == [(0, 2), (5, 10)]


def _words(*items):
    return Transcript(words=[Word(text=t, start=s, end=s + 0.3) for t, s in items])


def test_ending_prefers_claudes_pick_and_falls_back_to_the_last_sentence():
    tr = _words(("Hello", 0), ("there.", 1), ("It", 4), ("works.", 5), ("And", 8), ("I'd", 8.5), ("go.", 9))
    assert cuts.ending_word(tr, preferred=3) == 3
    assert cuts.ending_word(tr, preferred=1) == 6  # 1.3 s is not in the back half: use the last sentence end
    assert cuts.ending_word(tr, preferred=4) == 6  # "And" does not end a sentence
    assert cuts.ending_word(_words(("no", 0), ("stop", 5))) is None


def test_end_at_trims_after_the_last_word_and_keeps_the_hook():
    from hypercut.plan import Segment

    tr = _words(("It", 4), ("works.", 5), ("And", 8))
    segs = [Segment(start=8, end=9, reason="hook"), Segment(start=0, end=6.5), Segment(start=7, end=9.5)]
    out = cuts.end_at(segs, tr, 1)
    assert [(s.start, s.end, s.reason) for s in out] == [(8, 9, "hook"), (0, 5.7, "body")]


def test_analyze_ends_on_the_chosen_sentence(sample, fake_llm):
    words = sample.transcript.words
    last = max(i for i, w in enumerate(words) if cuts.SENTENCE_END.search(w.text))
    fake_llm({"ending": {"word": last}})
    p = run(sample)
    body = [s for s in p.segments if s.reason == "body"]
    assert body[-1].end <= words[last].end + cuts.END_TAIL + 1e-6


def test_recut_keeps_hook_and_ending(sample):
    p = run(sample)
    p.segments = cuts.end_at(p.segments, p.transcript, len(p.transcript.words) - 2)
    end_before = [s for s in p.segments if s.reason == "body"][-1].end
    p.style.pacing.keep_pause = 0.3
    q = cuts.recut(p)
    assert [s for s in q.segments if s.reason == "hook"] == [s for s in p.segments if s.reason == "hook"]
    assert [s for s in q.segments if s.reason == "body"][-1].end <= end_before + 0.3
    assert q.output_duration() >= p.output_duration()  # more pause kept, never less footage


def test_pauses_too_short_to_matter_are_not_cut():
    from hypercut.analyze.cuts import cut_ranges
    from hypercut.plan import Transcript, Word

    # 0.5 s gap minus 0.15 s kept each side leaves 0.2 s: not worth a jump cut. A 1 s gap is cut.
    t = Transcript(words=[Word(start=0, end=1, text="a"), Word(start=1.5, end=2, text="b"), Word(start=3, end=4, text="c")])
    assert cut_ranges(t, 4, max_silence=0.35, keep_pause=0.15) == [(2.15, 2.85)]


def test_green_screen_titles_and_backgrounds_only_when_on(sample, fake_llm):
    answer = {
        **GOOD,
        "behind": [{"start": 1.0, "end": 2.0, "text": "TEN HOURS A WEEK"}, {"start": 6.5, "end": 7.0, "text": "split"}],
        "backgrounds": [{"start": 6.0, "end": 9.0, "kind": "dim"}, {"start": 1, "end": 2, "kind": "lava"}],
    }
    calls = fake_llm(answer)
    off = run(sample)
    assert "behind" not in calls[0] and off.backgrounds == [] and all(g.layer == "front" for g in off.graphics)

    style = Style(depth={"enabled": True})
    p = run(sample, style=style)
    assert "BEHIND the speaker" in calls[1]
    behind = [g for g in p.graphics if g.layer == "behind"]
    assert [(g.id, g.props["text"]) for g in behind] == [("b1", "TEN HOURS A")]  # 3 words max
    assert not any(g.type == "stat_card" and g.start < 2.0 for g in p.graphics)  # the overlapped card made room
    assert [(b.kind, b.start) for b in p.backgrounds] == [("dim", 6.0)]


def test_behind_titles_skip_split_and_visual_stretches():
    from hypercut.analyze.analyze import add_behind
    from hypercut.plan import Graphic, LayoutSpan

    titles = [Graphic(id="", type="kinetic_text", start=1, end=2, props={"text": "A"}, layer="behind"),
              Graphic(id="", type="kinetic_text", start=6, end=7, props={"text": "B"}, layer="behind")]
    out = add_behind([], titles, [LayoutSpan(start=5, end=8, mode="split")])
    assert [g.props["text"] for g in out] == ["A"]


def test_effects_around_the_speaker_only_when_on(sample, fake_llm):
    answer = {**GOOD, "around": [{"type": "orbit", "start": 1.0, "end": 2.5, "items": ["🔥", "big money talk", "", "💡"]}]}
    calls = fake_llm(answer)
    assert not any(g.type == "orbit" for g in run(sample).graphics)
    assert "AROUND the speaker" not in calls[0]

    p = run(sample, style=Style(depth={"enabled": True}))
    assert "AROUND the speaker" in calls[1]
    orbit = next(g for g in p.graphics if g.type == "orbit")
    assert (orbit.id, orbit.props["items"]) == ("o1", ["🔥", "big money talk", "💡"])
    assert not any(g.type == "orbit" for g in run(sample, style=Style(depth={"enabled": True, "around": False})).graphics)


def test_effects_around_are_cleaned_and_capped():
    from hypercut.analyze.analyze import _around

    items = [
        {"type": "orbit", "start": 1.0, "end": 20.0, "items": ["A", "stack of gold coins today"]},
        {"type": "fly_out", "start": 2.0, "end": 3.0, "items": ["x"]},  # overlaps the orbit
        {"type": "particles", "start": 7.5, "end": 9.0, "kind": "glitter"},
        {"type": "lasers", "start": 10, "end": 11},
        {"type": "fly_out", "start": 12, "end": 13, "items": []},
        {"type": "fly_out", "start": 14, "end": 15, "items": ["🚀"]},
    ]
    out = _around(items, duration=30, limit=2)
    assert [(g.type, g.start, g.end, g.props) for g in out] == [
        ("orbit", 1.0, 7.0, {"items": ["A", "stack of gold"]}),  # capped at 6 s, 3 words an item
        ("particles", 7.5, 9.0, {"kind": "sparkles"}),  # unknown kind -> sparkles; the limit drops the last
    ]


def test_effects_around_skip_split_and_visual_stretches():
    from hypercut.analyze.analyze import add_around
    from hypercut.plan import Graphic, LayoutSpan

    fx = [Graphic(id="", type="particles", start=1, end=3, props={"kind": "bokeh"}),
          Graphic(id="", type="orbit", start=6, end=7, props={"items": ["A"]})]
    out = add_around([], fx, [LayoutSpan(start=5, end=8, mode="visual")])
    assert [(g.id, g.type) for g in out] == [("o1", "particles")]


def test_drawn_graphics_are_keyed_by_item():
    from hypercut.analyze.analyze import draw_around
    from hypercut.plan import Graphic

    asked = []

    def draw(names, accent):
        asked.append(names)
        return [None if n == "cloud" else {"viewBox": "0 0 400 400", "body": f"<g>{n}</g>"} for n in names]

    orbit = Graphic(id="o1", type="orbit", start=0, end=3, props={"items": ["rocket", "cloud"]})
    fly = Graphic(id="o2", type="fly_out", start=4, end=6, props={"items": ["rocket"]})
    assert draw_around([orbit, fly], Style(), draw)
    assert asked == [["cloud", "rocket"]]  # each name drawn once
    assert list(orbit.props["art"]) == ["rocket"] and fly.props["art"]["rocket"]["body"] == "<g>rocket</g>"
    orbit.props["items"] = ["rocket", "moon"]  # renamed in the editor: only the new one is drawn
    draw_around([orbit, fly], Style(), draw)
    assert asked[-1] == ["moon"] and set(orbit.props["art"]) == {"rocket", "moon"}
