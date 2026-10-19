from hypercut.analyze.cutaways import COVER, cover_cuts, jump_cuts
from hypercut.plan import EditPlan, Graphic, LayoutSpan, Segment, Source

SOURCE = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=60)
SEGS = [Segment(start=0, end=10), Segment(start=12, end=20), Segment(start=25, end=40)]


def _plan(graphics, layout=()):
    return EditPlan(source=SOURCE, segments=SEGS, graphics=list(graphics), layout=list(layout))


def test_jump_cuts_are_forward_skips():
    assert [(a1, b0) for _, a1, b0, _ in jump_cuts(_plan([]))] == [(10, 12), (20, 25)]


def test_a_visual_ending_just_before_a_cut_runs_across_it():
    g = Graphic(id="v1", type="illustration", start=7, end=9.6, props={})
    p = _plan([g], [LayoutSpan(start=7, end=9.6, mode="split")])
    assert cover_cuts(p) == 1
    assert g.end == 12 + COVER and p.layout[0].end == 12 + COVER  # the panel stays up through the jump


def test_a_visual_starting_just_after_a_cut_starts_before_it():
    g = Graphic(id="m1", type="motion", start=25.5, end=28, props={})
    p = _plan([g], [LayoutSpan(start=25.5, end=28, mode="visual")])
    cover_cuts(p)
    assert g.start == 20 - COVER and p.layout[0].start == 20 - COVER


def test_far_visuals_and_crowded_cuts_stay_put():
    far = Graphic(id="v1", type="illustration", start=2, end=5, props={})
    overlay = Graphic(id="t1", type="lower_third", start=8, end=9.8, props={})  # not a visual: no panel
    before = Graphic(id="v2", type="illustration", start=17, end=19.8, props={})
    after = Graphic(id="v3", type="media", start=25, end=26, props={})  # already on the far side
    p = _plan([far, overlay, before, after])
    assert cover_cuts(p) == 0
    assert (far.end, overlay.end, before.end, after.start) == (5, 9.8, 19.8, 25)
