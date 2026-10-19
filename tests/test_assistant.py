from hypercut import assistant, llm
from hypercut.plan import EditPlan, Graphic, LayoutSpan, Segment, Source, Transcript, Word, Zoom

SOURCE = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=20)
ART = {"viewBox": "0 0 1000 800", "defs": "", "layers": ["<g/>"]}


def _plan():
    words = [Word(text=f"w{i}", start=i, end=i + 0.5) for i in range(20)]
    return EditPlan(
        source=SOURCE,
        segments=[Segment(start=2, end=4, reason="hook"), Segment(start=0, end=20)],
        transcript=Transcript(words=words),
        graphics=[Graphic(id="v1", type="illustration", start=5, end=8, props={"title": "Rocket", **ART}),
                  Graphic(id="g1", type="kinetic_text", start=10, end=11, props={"text": "WOW"})],
        zooms=[Zoom(start=1, end=2), Zoom(start=1, end=2)],
        layout=[LayoutSpan(start=5, end=8, mode="split")],
    )


def test_summary_is_in_reel_time():
    s = assistant.summarize(_plan(), [{"name": "asset-0123456789ab.mp4", "kind": "video", "label": "beach"}])
    assert "v1: illustration, 7.0-10.0" in s["items"]  # source 5-8 plays at reel 7-10 after the 2 s hook
    assert "l0: split, 7.0-10.0" in s["layout"] and "beach" in s["assets"]
    assert s["captions"].startswith("0.2 w2 w3")


def test_apply_ops_delete_captions_and_illustration():
    drawn = []

    def draw(briefs):
        drawn.extend(briefs)
        return [ART]

    ops = [
        {"op": "delete", "keys": ["v1", "z1", "nope"]},
        {"op": "remove_captions", "start": 12, "end": 15},
        {"op": "add_illustration", "start": 16, "end": 19, "title": "Beach day", "brief": "a sunny beach", "layout": "split"},
        {"op": "edit", "key": "g1", "props": {"text": "NICE"}},
        {"op": "teleport"},
    ]
    plan, changes = assistant.apply_ops(_plan(), ops, playhead=0, assets=[], draw=draw)
    ids = {g.id: g for g in plan.graphics}
    assert "v1" not in ids and len(plan.zooms) == 1  # only the second of two equal zooms went
    assert ids["g1"].props["text"] == "NICE"
    new = ids["a1"]
    assert new.type == "illustration" and (new.start, new.end) == (14, 17) and drawn == ["a sunny beach"]
    assert any(s.mode == "split" and (s.start, s.end) == (14, 17) for s in plan.layout)
    assert [w.text for w in plan.transcript.words if 10 <= w.start < 13] == []
    assert any("caption" in c for c in changes)


def test_failed_drawing_falls_back_to_text_and_cuts_apply_last():
    ops = [{"op": "add_illustration", "start": 3, "end": 5, "title": "Plan"}, {"op": "cut", "start": 10, "end": 12}]
    plan, changes = assistant.apply_ops(_plan(), ops, playhead=0, assets=[], draw=lambda b: [None])
    g = plan.graphics[-1] if plan.graphics[-1].id == "a1" else next(x for x in plan.graphics if x.id == "a1")
    assert g.type == "kinetic_text" and g.props["text"] == "Plan" and (g.start, g.end) == (1, 3)
    assert plan.output_duration() == 20  # 22 s reel minus the 2 s cut
    assert any("drawing failed" in c for c in changes)


def test_add_media_uses_known_assets_only():
    assets = [{"name": "asset-0123456789ab.mp4", "kind": "video", "label": "beach", "duration": 3.0}]
    ops = [{"op": "add_media", "asset": "asset-0123456789ab.mp4", "start": 6, "layout": "visual"},
           {"op": "add_media", "asset": "../etc/passwd", "start": 6}]
    plan, _ = assistant.apply_ops(_plan(), ops, playhead=0, assets=assets)
    media = [g for g in plan.graphics if g.type == "media"]
    assert len(media) == 1 and media[0].props["src"] == "asset-0123456789ab.mp4"
    assert (media[0].start, media[0].end) == (4, 7)
    assert any(s.mode == "visual" and s.start == 4 for s in plan.layout)


def test_assist_calls_claude_once(monkeypatch):
    calls = []

    def fake(prompt, system="", **kw):
        calls.append(prompt)
        return {"message": "Removed the rocket.", "ops": [{"op": "delete", "keys": ["v1"]}]}

    monkeypatch.setattr(llm, "ask_json", fake)
    result = assistant.assist(_plan(), "remove the rocket illustration", playhead=3)
    assert result.message == "Removed the rocket." and "v1" not in {g.id for g in result.plan.graphics}
    assert len(calls) == 1 and "remove the rocket illustration" in calls[0]


def test_pacing_and_transition_ops():
    ops = [{"op": "pacing", "speed": 0.8}, {"op": "transitions", "style": "zoom", "fade_out": 1.2},
           {"op": "caption_style", "changes": {"font": "Bebas Neue"}}]
    plan, changes = assistant.apply_ops(_plan(), ops, playhead=0, assets=[])
    assert plan.style.pacing.speed == 0.8 and plan.style.transitions.style == "zoom"
    assert plan.style.transitions.fade_out == 1.2 and plan.style.caption.font == "Bebas Neue"
    assert plan.output_duration() == 22 / 0.8


def test_more_pause_recuts():
    p = _plan()
    plan, changes = assistant.apply_ops(p, [{"op": "pacing", "keep_pause": 0.3}], playhead=0, assets=[])
    assert plan.style.pacing.keep_pause == 0.3 and any("Re-cut" in c for c in changes)


def test_green_screen_ops():
    assets = [{"name": "asset-0123456789ab.jpg", "kind": "image", "label": "beach"}]
    ops = [
        {"op": "behind_text", "start": 12, "end": 14, "text": "BIG NEWS today folks"},
        {"op": "layer", "key": "v1", "layer": "behind"},
        {"op": "background", "kind": "media", "asset": "asset-0123456789ab.jpg", "start": 2, "end": 6, "parallax": 0.5},
        {"op": "background", "kind": "media", "asset": "missing.jpg"},
        {"op": "background", "kind": "blur"},
    ]
    plan, changes = assistant.apply_ops(_plan(), ops, playhead=0, assets=assets)
    assert plan.style.depth.enabled and plan.style.depth.background == "blur"
    b = next(g for g in plan.graphics if g.id == "b1")
    assert b.layer == "behind" and b.props["text"] == "BIG NEWS today" and (b.start, b.end) == (10, 12)
    assert next(g for g in plan.graphics if g.id == "v1").layer == "behind"
    assert plan.backgrounds == []  # the reel-wide blur came last and replaced the stretch
    plan2, _ = assistant.apply_ops(_plan(), ops[2:3], playhead=0, assets=assets)
    bg = plan2.backgrounds[0]
    assert (bg.kind, bg.src, bg.parallax, bg.start, bg.end) == ("media", "asset-0123456789ab.jpg", 0.5, 0, 4)
    off, _ = assistant.apply_ops(plan, [{"op": "depth", "enabled": False}], playhead=0, assets=[])
    assert not off.style.depth.enabled
    s = assistant.summarize(plan2, [])
    assert s["depth"].startswith("on") and "bg0: media" in s["backgrounds"]


def test_around_ops():
    ops = [
        {"op": "around", "type": "orbit", "start": 12, "end": 30, "items": ["🚀", "growth hacks now"]},
        {"op": "around", "type": "particles", "start": 2, "end": 4, "kind": "confetti"},
        {"op": "around", "type": "fly_out", "start": 5, "end": 6, "items": []},  # nothing to show
        {"op": "around", "type": "lasers", "start": 5, "end": 6},
    ]
    icons = lambda names, accent: [{"viewBox": "0 0 400 400", "body": "<g/>"} for _ in names]  # noqa: E731
    plan, changes = assistant.apply_ops(_plan(), ops, playhead=0, assets=[], draw_icons=icons)
    assert plan.style.depth.enabled and len(changes) == 2
    o1, o2 = (next(g for g in plan.graphics if g.id == i) for i in ("o1", "o2"))
    assert o1.type == "orbit" and o1.props["items"] == ["🚀", "growth hacks now"] and o1.end - o1.start == 6.0
    assert set(o1.props["art"]) == {"🚀", "growth hacks now"}
    assert o2.type == "particles" and o2.props == {"kind": "confetti"}
    assert all(l.mode == "speaker" for l in plan.layout if l.start < o1.end and o1.start < l.end)


def test_stage_ops():
    ops = [
        {"op": "stage", "type": "chart", "start": 12, "end": 30, "headline": "20 YEARS", "values": [1, 5, 20]},
        {"op": "stage", "type": "card_stack", "start": 2, "end": 5, "cards": [{"title": "Nurse", "brief": "a nurse"}]},
        {"op": "stage", "type": "scene", "start": 6, "end": 8, "brief": ""},  # nothing to draw
    ]
    art = {"viewBox": "0 0 1000 800", "defs": "", "layers": ["<g/>"]}
    plan, changes = assistant.apply_ops(_plan(), ops, playhead=0, assets=[], draw=lambda briefs, *a: [art for _ in briefs])
    assert plan.style.depth.enabled and len(changes) == 2
    chart, cards = (next(g for g in plan.graphics if g.id == i) for i in ("s1", "s2"))
    assert chart.type == "chart" and chart.props["values"] == [1.0, 5.0, 20.0] and chart.end - chart.start == 5.0
    assert cards.props["cards"][0]["layers"] == ["<g/>"]


def test_motion_graphic_and_animated_transition_ops():
    designed = []

    def design(prompt, system=""):
        designed.append(prompt)
        return {"scenes": [{"id": "m1", "scene": {"objects": [{"shape": "sphere", "radius": 1}]}}]}

    ops = [
        {"op": "motion", "start": 7, "end": 12, "title": "Rocket launch", "idea": "a rocket lifting off"},
        {"op": "cut_transition", "at": 14, "kind": "whip"},
        {"op": "cut_transition", "at": 16, "kind": "spin"},
    ]
    plan, changes = assistant.apply_ops(_plan(), ops, playhead=0, assets=[], design=design)
    m = next(g for g in plan.graphics if g.type == "motion")
    assert (m.start, m.end) == (5, 5 + 3.2) and m.props["scene"]["objects"][0]["shape"] == "sphere"
    assert "v1" not in {g.id for g in plan.graphics}  # the illustration there made way
    assert [(c.at, c.kind) for c in plan.cuts] == [(12, "whip")]  # reel 14 is source 12 after the hook
    assert any("motion graphic" in c for c in changes)
    plan, _ = assistant.apply_ops(plan, [{"op": "cut_transition", "at": 14.3, "kind": "none"}], playhead=0, assets=[])
    assert plan.cuts == []
