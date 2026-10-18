import pytest

from hypercut.matte import needs_matte, refine
from hypercut.matte.cutout import face_at, to_alpha
from hypercut.plan import EditPlan, Reframe, ReframeKey, Source, Style

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

SOURCE = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=20)


def _blob(mask, x0, y0, x1, y1, value=1.0):
    mask[y0:y1, x0:x1] = value
    return mask


def test_keeps_only_the_person_at_the_face():
    person = np.zeros((90, 160), np.float32)
    _blob(person, 10, 20, 40, 90)  # someone on the left
    _blob(person, 100, 10, 140, 90)  # the speaker on the right
    held = np.zeros_like(person)
    mask = refine(person, held, face=(0.75, 0.3))
    assert mask[50, 120] > 0.9 and mask[50, 25] == 0


def test_largest_person_without_a_face():
    person = np.zeros((90, 160), np.float32)
    _blob(person, 10, 60, 20, 90)
    _blob(person, 60, 10, 130, 90)
    mask = refine(person, np.zeros_like(person), face=None)
    assert mask[50, 100] > 0.9 and mask[80, 15] == 0


def test_held_object_inside_the_silhouette_comes_back_but_bleed_outside_does_not():
    person = np.zeros((90, 160), np.float32)
    _blob(person, 50, 10, 110, 90)
    person[50:70, 70:90] = 0  # a book the multi-class model calls background
    held = np.zeros_like(person)
    held[50:70, 70:90] = 1.0  # the selfie model keeps it...
    held[0:90, 0:20] = 1.0  # ...and bleeds into the wall
    mask = refine(person, held, face=(0.5, 0.2))
    assert mask[60, 80] > 0.9 and mask[50, 10] == 0


def test_smooths_within_a_shot_not_across_a_cut():
    a = _blob(np.zeros((90, 160), np.float32), 50, 10, 110, 90)
    b = _blob(np.zeros((90, 160), np.float32), 52, 10, 112, 90)
    first = refine(a, np.zeros_like(a), None)
    second = refine(b, np.zeros_like(b), None, prev=first)
    assert 0 < second[50, 51] < 1  # the edge eases instead of jumping
    other = _blob(np.zeros((90, 160), np.float32), 0, 40, 30, 90)  # a different shot
    cut = refine(other, np.zeros_like(other), None, prev=first)
    assert cut[50, 80] == 0


def test_alpha_ramp():
    alpha = to_alpha(np.array([[0.0, 0.35, 0.55, 0.75, 1.0]], np.float32))
    assert alpha[0, 0] == 0 and alpha[0, 1] == 0 and 100 < alpha[0, 2] < 155 and alpha[0, 3] == 255


def test_face_at_interpolates_keys():
    r = Reframe(keys=[ReframeKey(t=0, cx=0.2, cy=0.4), ReframeKey(t=2, cx=0.6, cy=0.4)])
    assert face_at(r, 1.0) == pytest.approx((0.4, 0.4))
    assert face_at(r, 5.0) == (0.6, 0.4) and face_at(Reframe(), 1.0) is None


def test_needs_matte_only_when_asked():
    plan = EditPlan(source=SOURCE)
    assert not needs_matte(plan)
    plan.style = Style(depth={"enabled": True})
    assert needs_matte(plan)


def test_titles_sit_where_the_head_covers_a_little():
    from hypercut.matte.titles import place_title
    from hypercut.plan import Graphic

    plan = EditPlan(source=SOURCE, reframe=Reframe(keys=[ReframeKey(t=0, cx=0.5, cy=0.45)]))
    head = np.zeros((270, 480), np.uint8)
    head[60:, 210:270] = 255  # a narrow head and neck from a quarter of the way down
    head[150:, 150:330] = 255  # shoulders
    g = Graphic(id="b1", type="kinetic_text", start=0, end=2, props={"text": "TEN X"}, layer="behind")
    place_title(g, plan, [(1.0, head)])
    assert g.layer == "behind" and 0.15 < g.props["y"] < 0.4

    closeup = np.full((270, 480), 255, np.uint8)  # the face fills the frame: no readable height
    g2 = Graphic(id="b2", type="kinetic_text", start=0, end=2, props={"text": "TEN X"}, layer="behind")
    place_title(g2, plan, [(1.0, closeup)])
    assert g2.layer == "front" and "y" not in g2.props
