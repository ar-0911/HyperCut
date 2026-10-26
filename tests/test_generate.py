import json

import pytest

from hypercut import generate as gen_pkg
from hypercut.generate import backends, fetch as gen, stock
from hypercut.generate.backends import Backend, Made
from hypercut.plan import EditPlan, Graphic, LayoutSpan, Segment, Source, Transcript, Word

SOURCE = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=20)
ART = {"viewBox": "0 0 10 10", "defs": "", "layers": ["<g/>"]}


@pytest.fixture(autouse=True)
def no_keys(monkeypatch):
    for k in ("FAL_KEY", "HYPERCUT_GEN_LOCAL", "PEXELS_API_KEY", "PIXABAY_API_KEY", "HYPERCUT_STOCK", "HYPERCUT_GEN_VIDEO",
              "HYPERCUT_GEN_BUDGET_USD"):
        monkeypatch.delenv(k, raising=False)


class FakeBackend(Backend):
    name = "fake"
    image_model = "fake-image"
    video_model = "fake-video"

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def image_cost(self):
        return 0.05

    def video_cost(self):
        return 0.5

    def image(self, prompt, out, seed=None):
        self.calls.append(("image", prompt, seed))
        if self.fail:
            raise backends.GenerateError("model down")
        out.write_bytes(b"jpg")
        return Made(out, "image", "fake-image", 0.05)

    def video(self, prompt, still, out, seed=None):
        self.calls.append(("video", prompt, still.name))
        out.write_bytes(b"mp4")
        return Made(out, "video", "fake-video", 0.5, duration=5.0)


def _plan(*graphics):
    return EditPlan(
        source=SOURCE, segments=[Segment(start=0, end=20)],
        transcript=Transcript(words=[Word(text="city", start=5, end=5.5), Word(text="lights.", start=5.6, end=6)]),
        graphics=list(graphics), layout=[LayoutSpan(start=4, end=8, mode="split")],
    )


def _picture(id="p1", **req):
    return Graphic(id=id, type="media", start=4, end=8,
                   props={"generate": {"kind": "image", "prompt": "a glowing city at night", "look": "3D render", **req},
                          "title": "City", "brief": "a city skyline at night"})


def test_nothing_set_up_means_nothing_offered():
    assert gen_pkg.available() == set()


def test_keys_turn_on_what_they_cover(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "k")
    assert gen_pkg.available() == {"stock"}
    monkeypatch.setenv("FAL_KEY", "k")
    assert gen_pkg.available() == {"stock", "image", "video"}
    monkeypatch.setenv("HYPERCUT_GEN_VIDEO", "0")
    assert gen_pkg.available() == {"stock", "image"}


def test_a_generated_still_fills_src_and_is_cached(tmp_path):
    backend = FakeBackend()
    plan = gen.generate(_plan(_picture()), tmp_path, backend=backend)
    g = plan.graphics[0]
    assert g.props["src"].startswith("gen-") and g.props["src"].endswith(".jpg") and g.props["kind"] == "image"
    assert (tmp_path / g.props["src"]).read_bytes() == b"jpg"
    assert "3D render" in backend.calls[0][1] and "No text" in backend.calls[0][1]
    assert json.loads((tmp_path / "generate.json").read_text())["spent"] == pytest.approx(0.05)
    # The same request again (e.g. after the editor dropped src) is served from the folder for free.
    again = gen.generate(_plan(_picture()), tmp_path, backend=backend)
    assert again.graphics[0].props["src"] == g.props["src"] and len(backend.calls) == 1
    assert gen.pending(again) == []


def test_a_clip_animates_its_own_still(tmp_path):
    backend = FakeBackend()
    moment = Graphic(id="m1", type="motion", start=10, end=13,
                     props={"title": "DNA", "idea": "a helix", "generate": {"kind": "video", "prompt": "a helix turning"}})
    plan = gen.generate(_plan(moment), tmp_path, backend=backend)
    props = plan.graphics[0].props
    assert props["src"].endswith(".mp4") and props["kind"] == "video" and props["duration"] == 5.0
    assert [c[0] for c in backend.calls] == ["image", "video"] and backend.calls[1][2] == props["poster"]


def test_over_budget_falls_back_to_a_drawing(tmp_path):
    drawn = []
    plan = gen.generate(_plan(_picture()), tmp_path, backend=FakeBackend(), limit=0.01,
                        draw=lambda briefs: drawn.extend(briefs) or [ART] * len(briefs))
    g = plan.graphics[0]
    assert g.type == "illustration" and g.props["title"] == "City" and drawn == ["a city skyline at night"]
    assert "budget" in g.props["generate"]["failed"]
    assert gen.spent(tmp_path)["spent"] == 0


def test_a_failed_call_is_refunded_and_falls_back_to_text_without_a_drawing(tmp_path):
    plan = gen.generate(_plan(_picture()), tmp_path, backend=FakeBackend(fail=True), draw=lambda b: [None] * len(b))
    g = plan.graphics[0]
    assert g.type == "kinetic_text" and g.props["text"] == "City"
    assert json.loads((tmp_path / "generate.json").read_text())["spent"] == 0


def test_without_a_backend_motion_moments_keep_their_3d_scene(tmp_path):
    moment = Graphic(id="m1", type="motion", start=10, end=13, props={"idea": "x", "scene": {"objects": []},
                                                                      "generate": {"kind": "video", "prompt": "x"}})
    plan = gen.generate(_plan(moment), tmp_path, backend=None)
    assert plan.graphics[0].type == "motion" and "failed" in plan.graphics[0].props["generate"]


def test_regenerate_asks_again_with_a_new_seed_and_prompt(tmp_path):
    plan = gen.generate(_plan(_picture()), tmp_path, backend=FakeBackend())
    again = gen.regenerate(plan, "p1", "a city at dawn")
    req = again.graphics[0].props["generate"]
    assert "src" not in again.graphics[0].props and req["prompt"] == "a city at dawn" and isinstance(req["seed"], int)
    # A picture that fell back to a drawing becomes a picture request again.
    other = tmp_path / "other"
    other.mkdir()
    fell = gen.generate(_plan(_picture()), other, backend=FakeBackend(fail=True), draw=lambda b: [ART] * len(b))
    back = gen.regenerate(fell, "p1")
    assert back.graphics[0].type == "media" and back.graphics[0].props["title"] == "City" and "layers" not in back.graphics[0].props


def test_stock_shots_carry_their_credit(tmp_path, monkeypatch):
    monkeypatch.setenv("HYPERCUT_STOCK", "commons")
    pick = stock.Candidate("commons", "image", "Skyline", "t", "u", "Jane, CC BY 4.0, Wikimedia Commons", "https://c/x",
                           credit_required=True)
    seen = {}
    monkeypatch.setattr(stock, "search", lambda q, media: seen.setdefault("q", (q, media)) and [pick])

    def fetch(c, stem):
        p = stem.with_suffix(".jpg")
        p.write_bytes(b"jpg")
        return p, None

    monkeypatch.setattr(stock, "fetch", fetch)
    g = Graphic(id="f1", type="media", start=4, end=8, props={"generate": {"kind": "stock", "query": "city skyline", "media": "image"},
                                                               "brief": "a skyline"})
    plan = gen.generate(_plan(g), tmp_path, backend=None, choose=lambda cands, brief, said: cands[0])
    props = plan.graphics[0].props
    assert seen["q"] == ("city skyline", "image")
    assert props["src"].endswith(".jpg") and props["credit_required"] and props["credit"].startswith("Jane")
    # Cached: no second search.
    monkeypatch.setattr(stock, "search", lambda q, media: pytest.fail("searched again"))
    gen.generate(_plan(g), tmp_path, backend=None, choose=lambda c, b, s: c[0])


def test_no_stock_shot_fits_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("HYPERCUT_STOCK", "commons")
    monkeypatch.setattr(stock, "search", lambda q, media: [])
    g = Graphic(id="f1", type="media", start=4, end=8, props={"generate": {"kind": "stock", "query": "x"}, "brief": "b", "title": "T"})
    plan = gen.generate(_plan(g), tmp_path, backend=None, draw=lambda b: [ART])
    assert plan.graphics[0].type == "illustration"


def test_fal_backend_queues_polls_and_downloads(tmp_path, monkeypatch):
    calls = []

    def http_json(method, url, headers=None, body=None, params=None):
        calls.append((method, url, body))
        if method == "POST":
            return {"status_url": "https://q/status", "response_url": "https://q/result"}
        if url.endswith("status"):
            return {"status": "COMPLETED"}
        return {"images": [{"url": "https://cdn/img.jpg"}]}

    monkeypatch.setattr(backends, "http_json", http_json)
    monkeypatch.setattr(backends, "download", lambda url, out, headers=None: out.write_bytes(b"x") and out)
    made = backends.FalBackend("key").image("a city", tmp_path / "a.jpg", seed=7)
    assert calls[0][1] == f"{backends.FAL_QUEUE}/{backends.FAL_IMAGE_MODEL}" and calls[0][2]["seed"] == 7
    assert calls[0][2]["image_size"] == {"width": 1080, "height": 1920}
    assert made.path.read_bytes() == b"x" and made.cost == backends.IMAGE_COST[backends.FAL_IMAGE_MODEL]
