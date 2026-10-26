import pytest

from hypercut.plan import Source
from hypercut.reframe import Detection, reframe, smooth_track

LANDSCAPE = Source(path="x.mp4", width=1920, height=1080, fps=30, duration=10)
VERTICAL = Source(path="x.mp4", width=1080, height=1920, fps=30, duration=10)
HALF = (1080 * 9 / 16) / 1920 / 2


def dets(xs, dt=0.2):
    return [Detection(i * dt, x, 0.4 if x is not None else None) for i, x in enumerate(xs)]


def test_no_face_is_center_crop():
    assert smooth_track(dets([None, None]), LANDSCAPE).keys == []


def test_vertical_source_has_no_keys_and_skips_detection():
    def boom(*a):
        raise AssertionError("detector should not run")

    assert reframe("x.mp4", VERTICAL, detector=boom).keys == []


def test_dead_zone_stops_jitter():
    keys = smooth_track(dets([0.5, 0.51, 0.49, 0.52, 0.5]), LANDSCAPE).keys
    assert {k.cx for k in keys} == {0.5}
    assert all(k.cy == 0.4 for k in keys)  # the face's height, for zooms and graphic placement


def test_follows_a_move_smoothly():
    keys = smooth_track(dets([0.4] * 3 + [0.6] * 30), LANDSCAPE).keys
    xs = [k.cx for k in keys]
    assert xs[0] == 0.4
    assert xs == sorted(xs)
    assert xs[3] < 0.5  # eased, not a jump
    assert xs[-1] == pytest.approx(0.6, abs=0.05)


def test_gaps_hold_and_leading_gap_backfills():
    keys = smooth_track(dets([None, 0.45, None, None]), LANDSCAPE).keys
    assert len(keys) == 4
    assert {k.cx for k in keys} == {0.45}


def test_crop_stays_inside_frame():
    keys = smooth_track(dets([0.0] * 5 + [1.0] * 60), LANDSCAPE).keys
    assert all(HALF - 1e-3 <= k.cx <= 1 - HALF + 1e-3 for k in keys)


def test_reframe_uses_injected_detector():
    seen = {}

    def fake(path, source, fps):
        seen["args"] = (path, fps)
        return dets([0.5, 0.5])

    out = reframe("v.mp4", LANDSCAPE, detector=fake)
    assert seen["args"] == ("v.mp4", 5.0)
    assert len(out.keys) == 2


def test_real_detector_importable_or_skipped():
    pytest.importorskip("mediapipe")
    pytest.importorskip("cv2")


def test_hard_cut_snaps_to_new_speaker_and_holds_until_the_cut():
    d = [Detection(0.0, 0.35), Detection(0.2, 0.35), Detection(0.4, 0.65, cut=True), Detection(0.6, 0.65)]
    keys = smooth_track(d, LANDSCAPE).keys
    assert keys[1].cx == pytest.approx(0.35)
    hold, snap = keys[2], keys[3]
    assert hold.t == pytest.approx(0.399) and hold.cx == pytest.approx(0.35)
    assert snap.t == pytest.approx(0.4) and snap.cx == pytest.approx(0.65)
    assert keys[-1].cx == pytest.approx(0.65)


def test_cut_without_a_face_yet_looks_ahead_within_the_shot():
    d = [Detection(0.0, 0.35), Detection(0.2, None, cut=True), Detection(0.4, 0.62), Detection(0.6, 0.62)]
    keys = smooth_track(d, LANDSCAPE).keys
    assert [k.cx for k in keys if k.t >= 0.2] == pytest.approx([0.62, 0.62, 0.62])


def test_cut_into_a_faceless_shot_centres_it():
    d = [Detection(0.0, 0.35), Detection(0.2, None, cut=True), Detection(0.4, None), Detection(0.6, 0.6, cut=True)]
    keys = smooth_track(d, LANDSCAPE).keys
    assert keys[1].cx == pytest.approx(0.35)  # held right up to the cut
    assert keys[2].cx == pytest.approx(0.5) and keys[3].cx == pytest.approx(0.5)
    assert keys[-1].cx == pytest.approx(0.6)


def test_face_height_follows_and_snaps_at_cuts():
    d = [Detection(0.0, 0.4, 0.3), Detection(0.2, 0.4, 0.3), Detection(0.4, 0.6, 0.7, cut=True), Detection(0.6, 0.6, 0.7)]
    keys = smooth_track(d, LANDSCAPE).keys
    assert keys[0].cy == pytest.approx(0.3)
    assert keys[2].cy == pytest.approx(0.3)  # held up to the cut
    assert keys[3].cy == pytest.approx(0.7) and keys[-1].cy == pytest.approx(0.7)


def test_missing_face_height_defaults_to_middle():
    keys = smooth_track([Detection(0.0, 0.4), Detection(0.2, 0.4)], LANDSCAPE).keys
    assert {k.cy for k in keys} == {0.5}


def test_tiles_cover_the_frame_with_overlap():
    from hypercut.reframe.track import tiles

    full, half = tiles(3414, 1920)
    assert all(side == 1920 for _, _, side in full) and full[0][0] == 0 and full[-1][0] + 1920 == 3414
    assert len(full) >= 2 and all(side == 960 for _, _, side in half)
    assert {y for _, y, _ in half} == {0, 480} and max(x for x, _, _ in half) + 960 == 3414
    # Neighbouring windows overlap, so a face on a seam is whole in one of them.
    xs = sorted({x for x, _, _ in half})
    assert all(b - a < 960 for a, b in zip(xs, xs[1:]))


def test_stray_detections_are_ignored():
    from hypercut.reframe.track import drop_outliers

    xs = [0.32, 0.6, 0.32, 0.31, 0.6, 0.32, 0.33]
    d = [Detection(i * 0.2, x) for i, x in enumerate(xs)] + [Detection(1.4, 0.7, cut=True), Detection(1.6, 0.71)]
    kept = [x.cx for x in drop_outliers(d)]
    assert kept == [0.32, None, 0.32, 0.31, None, 0.32, 0.33, 0.7, 0.71]  # the next shot is judged on its own
    keys = smooth_track(d, LANDSCAPE).keys
    assert all(abs(k.cx - 0.32) < 0.03 for k in keys if k.t < 1.39)


def test_follows_the_shots_main_face_not_the_biggest_one():
    from hypercut.reframe.track import follow_main_face

    face, shirt, other = (0.32, 0.24, 0.9), (0.6, 0.47, 0.8), (0.75, 0.3, 0.6)
    frames = [(face, shirt), (shirt,), (face, shirt), (face,), (face, shirt, other), (face, shirt)]
    # The detector's own pick (cx) is the shirt, the biggest "face" in most frames.
    d = [Detection(i * 0.2, 0.6, 0.47, candidates=c) for i, c in enumerate(frames)]
    d.append(Detection(1.2, 0.5, 0.3, cut=True, candidates=((0.5, 0.3, 0.9),)))
    picked = [x.cx for x in follow_main_face(d)]
    assert picked == [0.32, None, 0.32, 0.32, 0.32, 0.32, 0.5]


def test_main_face_is_followed_as_it_moves():
    from hypercut.reframe.track import follow_main_face

    xs = [0.3, 0.35, 0.4, 0.45, 0.5, 0.55]
    d = [Detection(i * 0.2, x, 0.3, candidates=((x, 0.3, 0.9), (0.8, 0.6, 0.6))) for i, x in enumerate(xs)]
    assert [x.cx for x in follow_main_face(d)] == xs


def test_hard_cuts_are_kept_as_shots_for_transitions():
    d = [Detection(0.0, 0.35), Detection(0.2, 0.35), Detection(0.4, 0.65, cut=True), Detection(0.6, None, cut=True)]
    assert smooth_track(d, LANDSCAPE).shots == [0.4, 0.6]
    assert smooth_track([Detection(0.0, None), Detection(0.2, None, cut=True)], LANDSCAPE).shots == [0.2]


def _two_people(talker, seconds=10, fps=5):
    """Two people at x 0.3 and 0.7 for `seconds`; talker(t) says who is talking (0, 1 or None)."""
    out = []
    for k in range(seconds * fps):
        t = k / fps
        who = talker(t)
        wobble = lambda p: (0.1 + 0.3 * (k % 2)) if who == p else 0.1  # noqa: E731
        out.append(Detection(t, 0.3, 0.5, candidates=((0.3, 0.5, 0.9), (0.7, 0.5, 0.9)), mouths=(wobble(0), wobble(1))))
    return out


def test_crop_follows_whoever_is_talking():
    dets = _two_people(lambda t: 0 if t < 5 else 1)
    r = smooth_track(dets, LANDSCAPE)
    at = lambda t: min(r.keys, key=lambda k: abs(k.t - t)).cx  # noqa: E731
    assert at(2) < 0.5 < at(8)  # left person, then the right one
    assert len(r.switches) == 1 and 4.4 <= r.switches[0] <= 5.2 and r.shots == []
    # The move is a jump, not a pan: the key just before the switch is still on the left person.
    before = max((k for k in r.keys if k.t < r.switches[0]), key=lambda k: k.t)
    assert before.cx < 0.5


def test_a_short_interjection_does_not_flip_the_frame():
    dets = _two_people(lambda t: 1 if 4 <= t < 4.6 else 0)
    r = smooth_track(dets, LANDSCAPE)
    assert r.switches == [] and all(k.cx < 0.5 for k in r.keys)


def test_without_mouth_readings_the_main_face_is_kept():
    dets = [Detection(k / 5, 0.3, 0.5, candidates=((0.3, 0.5, 0.9), (0.7, 0.5, 0.6))) for k in range(50)]
    r = smooth_track(dets, LANDSCAPE)
    assert r.switches == [] and all(k.cx < 0.5 for k in r.keys)


def test_switches_are_explained():
    from hypercut import explain
    from hypercut.plan import EditPlan, Reframe, Transcript, Word

    plan = EditPlan(source=LANDSCAPE, transcript=Transcript(words=[Word(text="hi", start=0, end=1)]),
                    reframe=Reframe(switches=[4.0]))
    items = explain.first_cut(plan)["items"]
    assert any(it["kind"] == "speaker" and abs(it["at"] - 4.0) < 0.02 for it in items)
