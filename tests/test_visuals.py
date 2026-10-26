import pytest

from hypercut import llm
from hypercut.analyze import visuals as vis
from hypercut.plan import Graphic, LayoutSpan, Segment, Style, Transcript, Word


def words(*specs):
    """specs: (text, start) pairs, each word 0.4 s long."""
    return Transcript(words=[Word(text=t, start=s, end=s + 0.4) for t, s in specs])


SPEECH = words(
    ("I", 0.0), ("love", 0.5), ("my", 1.0), ("morning", 1.5), ("shake.", 2.0),
    ("It", 3.0), ("keeps", 3.5), ("me", 4.0), ("going", 4.5), ("all", 5.0), ("day.", 5.5),
    ("My", 6.5), ("kids", 7.0), ("love", 7.5), ("it", 8.0), ("too.", 8.5),
)
SEGMENTS = [Segment(start=0.0, end=9.0)]
SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 800">'
    '<defs><linearGradient id="g"><stop offset="0" stop-color="#fff"/></linearGradient></defs>'
    '<g><rect width="1000" height="800" fill="url(#g)"/></g><g><circle cx="500" cy="400" r="100"/></g></svg>'
)


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []

    def install(director, svg=SVG):
        def ask_json(prompt, system="", timeout=300, web_search=False):
            calls.append((prompt, web_search))
            if prompt.startswith("Draw one SVG"):
                n = prompt.count("\n", prompt.index("Briefs:"), prompt.index("Return")) - 2
                return {"svgs": [{"i": i, "svg": svg} for i in range(n)]}
            return director

        monkeypatch.setattr(llm, "ask_json", ask_json)
        return calls

    return install


def test_beats_tile_the_kept_range_and_break_at_sentences():
    beats = vis.make_beats(SPEECH, SEGMENTS, 9.0)
    assert [b.text for b in beats] == ["I love my morning shake.", "It keeps me going all day.", "My kids love it too."]
    assert beats[0].start == 0.0 and beats[-1].end == 9.0
    assert all(a.end == b.start for a, b in zip(beats, beats[1:]))


def test_beats_skip_cut_words_and_count_only_played_time():
    beats = vis.make_beats(SPEECH, [Segment(start=0.0, end=2.5), Segment(start=6.4, end=9.0)], 9.0)
    assert "keeps" not in " ".join(b.text for b in beats)
    assert sum(b.kept for b in beats) == pytest.approx(5.1)


def test_no_speech_no_visuals():
    assert vis.plan_visuals(Transcript(), SEGMENTS, 9.0, Style()) == ([], [])


def test_plan_visuals_builds_layout_and_illustrations(fake_llm):
    calls = fake_llm({"beats": [
        {"i": 0, "mode": "speaker", "visual": None},
        {"i": 1, "mode": "split", "visual": {"kind": "illustration", "title": "All day", "brief": "a sun rising over a shaker bottle"}},
        {"i": 2, "mode": "visual", "visual": {"kind": "kinetic_text", "text": "KIDS LOVE IT"}},
    ]})
    layout, graphics = vis.plan_visuals(SPEECH, SEGMENTS, 9.0, Style())
    assert [s.mode for s in layout] == ["speaker", "split", "visual"]
    assert [g.type for g in graphics] == ["illustration", "kinetic_text"]
    art = graphics[0].props
    assert art["title"] == "All day" and art["viewBox"] == "0 0 1000 800" and len(art["layers"]) == 2
    assert 'id="g"' in art["defs"] and "xmlns" not in art["layers"][0]
    assert calls[0][1] is True  # the director may search the web for reference
    assert calls[1][1] is False and "shaker bottle" in calls[1][0]


def test_constraints_on_visual_only_beats(fake_llm):
    fake_llm({"beats": [{"i": i, "mode": "visual", "visual": {"kind": "kinetic_text", "text": "x"}} for i in range(3)]})
    layout, _ = vis.plan_visuals(SPEECH, SEGMENTS, 9.0, Style())
    modes = [m for s in layout for m in [s.mode]]
    assert modes[0] == "split"  # never open on a visual-only beat
    assert "visual" not in [modes[i] for i in range(len(modes)) if i and modes[i - 1] == "visual"]


def test_failed_drawing_falls_back_to_title_text(fake_llm):
    fake_llm({"beats": [
        {"i": 0, "mode": "split", "visual": {"kind": "illustration", "title": "Morning", "brief": "sunrise"}},
        {"i": 1, "mode": "split", "visual": {"kind": "illustration", "title": "", "brief": "a clock"}},
        {"i": 2, "mode": "bogus"},
    ]}, svg="not svg")
    layout, graphics = vis.plan_visuals(SPEECH, SEGMENTS, 9.0, Style())
    assert [(g.type, g.props) for g in graphics] == [("kinetic_text", {"text": "Morning"})]
    assert [s.mode for s in layout] == ["split", "speaker"]  # untitled failure and junk fall back


def test_svg_sanitizer_strips_active_content():
    out = vis.svg_layers(
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
        '<script>alert(1)</script><style>*{}</style><image href="http://x/a.png"/>'
        '<g onclick="x()" fill="url(#ok)"><rect style="fill:url(http://evil)" width="1"/>'
        '<use xlink:href="http://x"/><use href="#ok"/><foreignObject/></g></svg>'
    )
    layer = "".join(out["layers"])
    for bad in ("script", "style=", "image", "onclick", "http://", "foreignObject"):
        assert bad not in layer
    assert 'fill="url(#ok)"' in layer and 'href="#ok"' in layer
    assert out["viewBox"] == vis.VIEWBOX


@pytest.mark.parametrize("bad", ["", "<svg", "<html/>", '<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>'])
def test_svg_sanitizer_rejects_unusable_input(bad):
    with pytest.raises(ValueError):
        vis.svg_layers(bad)


def test_merge_keeps_overlays_and_drops_panel_graphics_in_busy_beats():
    existing = [
        Graphic(id="g1", type="kinetic_text", start=3.5, end=4.5, props={"text": "x"}),
        Graphic(id="g2", type="lower_third", start=3.5, end=6.0, props={"title": "Dawn"}),
        Graphic(id="g3", type="stat_card", start=0.5, end=1.5, props={"value": "1"}),
    ]
    art = [Graphic(id="v1", type="illustration", start=3.0, end=6.5, props={"layers": ["<g/>"]})]
    layout = [LayoutSpan(start=0.0, end=3.0, mode="speaker"), LayoutSpan(start=3.0, end=6.5, mode="split")]
    assert [g.id for g in vis.merge_graphics(existing, art, layout)] == ["g3", "v1", "g2"]


def test_director_offers_footage_and_pictures_only_when_they_can_be_fetched(fake_llm):
    calls = fake_llm({"look": "editorial 3D render, coral accents", "beats": [
        {"i": 0, "mode": "speaker", "visual": None},
        {"i": 1, "mode": "split", "visual": {"kind": "footage", "query": "busy morning kitchen", "media": "video",
                                             "title": "All day", "brief": "a kitchen at sunrise"}},
        {"i": 2, "mode": "split", "visual": {"kind": "picture", "prompt": "a shaker bottle glowing on a counter", "title": "Kids"}},
    ]})
    layout, graphics = vis.plan_visuals(SPEECH, SEGMENTS, 9.0, Style(), sources={"stock", "image"})
    assert "kind\": \"footage\"" in calls[0][0] and '"look"' in calls[0][0]
    assert [g.type for g in graphics] == ["media", "media"]
    stock_req, pic_req = graphics[0].props["generate"], graphics[1].props["generate"]
    assert stock_req == {"kind": "stock", "query": "busy morning kitchen", "media": "video"}
    assert pic_req["kind"] == "image" and pic_req["look"] == "editorial 3D render, coral accents"
    assert graphics[0].props["brief"] == "a kitchen at sunrise" and "src" not in graphics[0].props
    assert graphics[0].props["move"] != graphics[1].props["move"]
    assert [s.mode for s in layout] == ["speaker", "split"]


def test_without_sources_footage_is_ignored(fake_llm):
    calls = fake_llm({"beats": [{"i": 1, "mode": "split", "visual": {"kind": "footage", "query": "kitchen", "title": "x"}}]})
    layout, graphics = vis.plan_visuals(SPEECH, SEGMENTS, 9.0, Style())
    assert graphics == [] and "footage" not in calls[0][0]
