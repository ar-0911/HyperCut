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
