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


def test_cut_into_a_faceless_shot_holds_position():
    d = [Detection(0.0, 0.35), Detection(0.2, None, cut=True), Detection(0.4, None), Detection(0.6, 0.6, cut=True)]
    keys = smooth_track(d, LANDSCAPE).keys
    assert keys[1].cx == pytest.approx(0.35) and keys[2].cx == pytest.approx(0.35)
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
