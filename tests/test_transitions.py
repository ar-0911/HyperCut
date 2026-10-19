from hypercut.analyze.transitions import MIN_GAP, plan_transitions
from hypercut.plan import EditPlan, Graphic, LayoutSpan, Reframe, Segment, Source

SOURCE = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=90)


def _plan(shots, layout=(), hook=True, graphics=()):
    segs = [Segment(start=60, end=64, reason="hook"), Segment(start=0, end=90)] if hook else [Segment(start=0, end=90)]
    return EditPlan(source=SOURCE, segments=segs, reframe=Reframe(shots=list(shots)), layout=list(layout), graphics=list(graphics))


def test_cold_open_hands_over_with_a_drop_and_shot_changes_vary():
    cuts = plan_transitions(_plan([20, 40, 60.5, 70]))
    assert cuts[0].at == 0 and cuts[0].kind == "drop"  # the body starts after the 4 s hook
    assert [c.at for c in cuts[1:]] == [20, 40, 70]
    kinds = [c.kind for c in cuts]
    assert all(a != b for a, b in zip(kinds, kinds[1:]))


def test_sparing_and_spaced_out():
    cuts = plan_transitions(_plan([10, 12, 30, 31, 50], hook=False))
    assert [c.at for c in cuts] == [10, 30, 50]
    out = [c.at for c in cuts]
    assert all(b - a >= MIN_GAP for a, b in zip(out, out[1:]))
    many = plan_transitions(_plan([5 + i * 13 for i in range(7)], hook=False))
    assert len(many) <= 4  # about three a minute of a 90 s reel


def test_only_onto_the_speaker_alone_and_never_at_the_edges():
    layout = [LayoutSpan(start=19, end=25, mode="split")]
    graphics = [Graphic(id="m1", type="motion", start=39, end=42, props={})]
    cuts = plan_transitions(_plan([1, 20, 40, 89], layout=layout, hook=False, graphics=graphics))
    assert cuts == []
    # A shot change in a cut-out stretch never plays.
    p = _plan([30], hook=False)
    p.segments = [Segment(start=0, end=25), Segment(start=35, end=90)]
    assert plan_transitions(p) == []


def test_no_segments_means_nothing_to_do():
    p = EditPlan(source=SOURCE)
    assert plan_transitions(p) == []
