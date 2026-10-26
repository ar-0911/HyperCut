import pytest

from hypercut import edit
from hypercut.plan import EditPlan, Graphic, LayoutSpan, Segment, Source, Transcript, Word

SOURCE = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=20)


def _plan(**kw):
    # Cold open: source 10-12 plays first, then the body 0-8 and 9-20 (8-9 cut).
    segs = [Segment(start=10, end=12, reason="hook"), Segment(start=0, end=8), Segment(start=9, end=20)]
    return EditPlan(source=SOURCE, segments=segs, **kw)


def test_reel_source_mapping():
    p = _plan()
    assert edit.reel_duration(p) == pytest.approx(21)
    assert edit.to_source(p, 1.0) == (11.0, 0)
    assert edit.to_source(p, 3.0) == (1.0, 1)
    assert edit.to_source(p, 10.5) == (9.5, 2)
    assert edit.to_source(p, 99) == (20, 2)
    assert edit.to_reel(p, 11.0) == [1.0, 12.0]  # hook plays twice
    assert edit.to_reel(p, 8.5) == []  # cut
    assert edit.first_reel(p, 1, 3) == (3, 5)


def test_source_span_never_reverses_across_the_hook_jump():
    p = _plan()
    assert edit.source_span(p, 1.0, 4.0) == (11.0, 12.0)  # stops at the end of the hook piece
    assert edit.source_span(p, 9.0, 12.0) == (7.0, 11.0)  # crosses the 8-9 cut: fine, cut part is unseen


def test_remove_captions_by_reel_time():
    words = [Word(text=t, start=s, end=s + 0.4) for t, s in (("a", 0.5), ("b", 3.0), ("c", 10.5), ("d", 15.0))]
    p = _plan(transcript=Transcript(words=words))
    assert edit.remove_captions(p, 2.0, 6.0) == 2  # "a" at reel 2.7 and "b" at reel 5.2
    assert [w.text for w in p.transcript.words] == ["c", "d"]


def test_cut_splits_segments():
    p = _plan()
    removed = edit.cut(p, 4.0, 6.0)  # source 2-4 of the body
    assert removed == pytest.approx(2)
    assert [(s.start, s.end) for s in p.segments] == [(10, 12), (0, 2), (4, 8), (9, 20)]
    with pytest.raises(ValueError):
        edit.cut(p, 0, 100)


def test_set_layout_trims_and_splits():
    p = _plan(layout=[LayoutSpan(start=0, end=10, mode="split")])
    edit.set_layout(p, 4, 6, "visual")
    assert [(s.start, s.end, s.mode) for s in p.layout] == [(0, 4, "split"), (4, 6, "visual"), (6, 10, "split")]
    edit.set_layout(p, 3, 7, "speaker")
    assert [(s.start, s.end, s.mode) for s in p.layout] == [(0, 3, "split"), (7, 10, "split")]


def test_new_ids_do_not_collide():
    p = _plan(graphics=[Graphic(id="a1", type="kinetic_text", start=0, end=1)])
    g = edit.add_graphic(p, "kinetic_text", 2, 3, {"text": "hi"})
    assert g.id == "a2" and [x.id for x in p.graphics] == ["a1", "a2"]


def test_clear_visuals_makes_room():
    p = _plan(graphics=[
        Graphic(id="v1", type="illustration", start=0, end=4),
        Graphic(id="v2", type="illustration", start=5, end=12),
        Graphic(id="e1", type="emoji_burst", start=5, end=6),
        Graphic(id="new", type="media", start=4.5, end=7),
    ])
    assert edit.clear_visuals(p, 4.5, 7, keep="new") == []
    assert {g.id: (g.start, g.end) for g in p.graphics} == {"v1": (0, 4), "v2": (7, 12), "e1": (5, 6), "new": (4.5, 7)}
    assert edit.clear_visuals(p, 6, 12, keep="new") == ["v2"]


def test_mapping_follows_the_speed():
    p = _plan()
    p.style.pacing.speed = 0.5  # half speed: every reel second shows half a source second
    assert edit.reel_duration(p) == pytest.approx(42)
    assert edit.to_source(p, 2.0) == (11.0, 0)
    assert edit.to_reel(p, 1.0) == [6.0]
    assert edit.cut(p, 6.0, 10.0) == pytest.approx(4)  # reel 6-10 is source 1-3
    assert [(s.start, s.end) for s in p.segments][:3] == [(10, 12), (0, 1), (3, 8)]


def _spoken():
    # "a b" then a 1.5 s pause, then "c d", one piece.
    words = [Word(text="a", start=0, end=0.5), Word(text="b", start=0.6, end=1.0),
             Word(text="c", start=2.5, end=3.0), Word(text="d", start=3.1, end=3.5)]
    return EditPlan(source=SOURCE, transcript=Transcript(words=words), segments=[Segment(start=0, end=20)])


def test_pause_near_and_pause_cut():
    p = _spoken()
    assert edit.pauses(p) == [(1.0, 2.5)]
    assert edit.pause_near(p, 2.5, "before") == (1.0, 2.5)
    assert edit.pause_near(p, 1.0, "after") == (1.0, 2.5)
    assert edit.pause_near(p, 10, "nearest") is None
    a, b = edit.pause_cut(p, (1.0, 2.5))
    assert (a, b) == pytest.approx((1.15, 2.35))  # the style's 0.15 s kept on each side
    edit.cut(p, a, b)
    assert edit.pauses(p) == []


def test_word_cut_never_clips_a_word():
    p = _spoken()
    # Asked to cut 0.4-0.9: that covers the middle of "b" only (a's middle is 0.25).
    assert edit.word_cut(p, 0.4, 0.9) == pytest.approx((0.6, 1.75))  # from b to just before c, less the pause
    assert edit.word_cut(p, 5, 6) is None
