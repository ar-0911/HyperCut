from hypercut.analyze import motion
from hypercut.plan import EditPlan, Graphic, LayoutSpan, Segment, Source, Style, Transcript, Word

SOURCE = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=30)
HELIX = {"shape": "helix", "count": 20, "height": 5, "radius": 0.8, "anim": [{"type": "spin", "speed": 0.9}]}


def _plan():
    return EditPlan(
        source=SOURCE,
        segments=[Segment(start=0, end=30)],
        transcript=Transcript(words=[Word(text=f"w{i}", start=i, end=i + 0.5) for i in range(30)]),
        graphics=[
            Graphic(id="v1", type="illustration", start=9, end=12, props={"title": "Old"}),
            Graphic(id="s1", type="card_stack", start=4, end=7, props={"cards": []}),
            Graphic(id="g1", type="lower_third", start=4, end=6, props={"title": "Name"}),
        ],
        layout=[LayoutSpan(start=9, end=12, mode="split")],
    )


def test_clean_scene_keeps_only_what_can_be_drawn():
    scene = motion.clean_scene({
        "look": "dark",
        "objects": [
            HELIX,
            {"shape": "lathe"},  # no profile: nothing to turn
            {"shape": "hologram"},
            {"shape": "extrude", "path": "M0 0 L1 1 Z\"><script>"},  # not path data
            {"shape": "box", "size": [99, 1, 1], "position": [0, 0, 500], "anim": "spin", "color": "red"},
        ],
        "camera": {"orbit": 400, "push": 0.1, "zoom": 3},
    })
    assert scene["look"] == "dark" and scene["camera"] == {"orbit": 40, "push": 0.1}
    assert [o["shape"] for o in scene["objects"]] == ["helix", "box"]
    box = scene["objects"][1]
    assert box["size"] == [12, 1, 1] and box["position"] == [0, 0, 20] and "anim" not in box and "color" not in box
    assert motion.clean_scene({"objects": [{"shape": "group", "children": []}]}) is None
    assert motion.clean_scene({"look": "neon", "objects": [HELIX]}).get("look") is None


def test_parse_motion_keeps_short_spaced_moments_after_the_opening():
    items = [
        {"start": 1, "end": 3, "title": "Too early", "idea": "x"},
        {"start": 5, "end": 9, "title": "A long title of many words", "idea": "a paint can"},
        {"start": 6, "end": 8, "title": "Overlaps", "idea": "y"},
        {"start": 12, "end": 13, "title": "Too short", "idea": "z"},
        {"start": 15, "end": 17.5, "title": "No idea"},
        {"start": 20, "end": 22.5, "title": "Bell", "idea": "a desk bell"},
        "nonsense",
    ]
    out = motion.parse_motion(items, 30, limit=5)
    assert [(g.start, g.end) for g in out] == [(5, 5 + motion.MAX_SECONDS), (20, 22.5)]
    assert out[0].props == {"title": "A long title of", "idea": "a paint can"}
    assert len(motion.parse_motion(items, 30, limit=1)) == 1


def test_add_motion_takes_the_whole_frame():
    p = _plan()
    motion.add_motion(p, [Graphic(id="", type="motion", start=5, end=7.5, props={"title": "T", "idea": "i"}),
                          Graphic(id="", type="motion", start=10, end=12, props={"title": "U", "idea": "j"})])
    ids = [g.id for g in p.graphics]
    assert "m1" in ids and "m2" in ids
    assert "s1" not in ids and "v1" not in ids  # the stage card and the illustration under it make way
    assert "g1" in ids  # a name tag is not a visual
    assert any(s.mode == "visual" and (s.start, s.end) == (5, 7.5) for s in p.layout)


def test_design_scenes_fills_only_missing_scenes_and_never_fails_the_edit():
    gs = [Graphic(id="m1", type="motion", start=5, end=7, props={"title": "DNA", "idea": "a helix"}),
          Graphic(id="m2", type="motion", start=9, end=11, props={"title": "Done", "idea": "x", "scene": {"objects": [HELIX]}})]
    t = Transcript(words=[Word(text="DNA", start=5.2, end=5.6)])
    prompts = []

    def ask(prompt, system=""):
        prompts.append(prompt)
        return {"scenes": [{"id": "m1", "scene": {"objects": [HELIX], "look": "light"}}]}

    assert motion.design_scenes(gs, t, Style(), ask)
    assert gs[0].props["scene"]["look"] == "light" and len(prompts) == 1
    assert '"DNA"' in prompts[0] and '"m2"' not in prompts[0]
    assert not motion.design_scenes(gs, t, Style(), ask)  # nothing left to design

    def boom(prompt, system=""):
        raise RuntimeError("usage limit")

    fresh = [Graphic(id="m3", type="motion", start=1, end=3, props={"title": "x", "idea": "y"})]
    assert not motion.design_scenes(fresh, t, Style(), boom) and "scene" not in fresh[0].props
