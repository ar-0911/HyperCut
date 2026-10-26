import json

import pytest

from hypercut import diff, edit, explain, history
from hypercut import plan as plan_mod
from hypercut.plan import EditPlan, Graphic, Hook, HookCandidate, Segment, Source, Transcript, Word

SOURCE = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=20)


def _plan(**kw):
    words = [Word(text=f"w{i}", start=i, end=i + 0.5) for i in range(20)]
    return EditPlan(source=SOURCE, transcript=Transcript(words=words), segments=[Segment(start=0, end=20)], **kw)


def _project(tmp_path):
    plan = _plan()
    history.commit(tmp_path, plan, "pipeline", changes=[])
    return plan


def test_commit_undo_redo_survive_on_disk(tmp_path):
    p1 = _project(tmp_path)
    p2 = p1.model_copy(deep=True)
    edit.cut(p2, 2, 4)
    v2 = history.commit(tmp_path, p2)
    assert v2.id == 2 and v2.parent == 1 and v2.changes[0].startswith("Removed 2.0 s at 0:02.0")
    assert history.commit(tmp_path, p2).id == 2  # nothing changed: no new version

    plan, v = history.undo(tmp_path)
    assert v.id == 1 and plan_mod.load(tmp_path / "plan.json") == p1 == plan
    listing = history.listing(tmp_path)  # read back from disk, as after a reload
    assert listing["head"] == 1 and listing["can_redo"] and not listing["can_undo"]
    with pytest.raises(LookupError):
        history.undo(tmp_path)
    plan, v = history.redo(tmp_path)
    assert v.id == 2 and plan == p2


def test_new_edit_after_undo_keeps_the_old_branch(tmp_path):
    p1 = _project(tmp_path)
    p2 = p1.model_copy(update={"zooms": [plan_mod.Zoom(start=1, end=2)]})
    history.commit(tmp_path, p2)
    history.undo(tmp_path)
    p3 = p1.model_copy(deep=True)
    p3.style.caption.font = "Inter"
    v3 = history.commit(tmp_path, p3)
    assert v3.parent == 1 and not history.listing(tmp_path)["can_redo"]
    assert history.load_version(tmp_path, 2) == p2  # still there to go back to
    v4 = history.restore(tmp_path, 2)
    assert v4.kind == "restore" and "version 2" in v4.note and plan_mod.load(tmp_path / "plan.json") == p2
    assert "Caption font: Inter → Montserrat" in v4.changes


def test_named_versions_are_never_pruned(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "MAX_VERSIONS", 4)
    p = _project(tmp_path)
    for i in range(1, 9):
        p = p.model_copy(deep=True)
        p.style.pacing.speed = 1 + i / 20
        v = history.commit(tmp_path, p)
        if i == 2:
            history.name(tmp_path, v.id, "  Good cut ")
    ids = [v["id"] for v in history.listing(tmp_path)["versions"]]
    assert len(ids) == 4 and 1 in ids and 3 in ids and ids[0] == 9
    assert history.listing(tmp_path)["versions"][-2]["label"] == "Good cut"
    assert not (tmp_path / "history" / "v0002.json").exists()


def test_old_jobs_get_a_history_from_base_and_current(tmp_path):
    base = _plan()
    current = base.model_copy(update={"zooms": [plan_mod.Zoom(start=1, end=2)]})
    plan_mod.save(base, tmp_path / "plan.base.json")
    plan_mod.save(current, tmp_path / "plan.json")
    versions = history.listing(tmp_path)["versions"]
    assert [v["kind"] for v in versions] == ["edit", "pipeline"]
    assert versions[0]["changes"] == ["Added a zoom at 0:01.0-0:02.0"]


def test_draft_autosave_and_recovery(tmp_path):
    p1 = _project(tmp_path)
    assert history.draft(tmp_path) is None
    p2 = p1.model_copy(deep=True)
    p2.graphics = [Graphic(id="g1", type="kinetic_text", start=3, end=4, props={"text": "WOW"})]
    saved = history.save_draft(tmp_path, p2)
    assert saved["base"] == 1
    d = history.draft(tmp_path)
    assert d["changes"] == ["Added a big text “WOW” at 0:03.0-0:04.0"] and EditPlan.model_validate(d["plan"]) == p2
    history.commit(tmp_path, p2)  # saving clears it
    assert history.draft(tmp_path) is None
    (tmp_path / "draft.json").write_text("{not json")
    assert history.draft(tmp_path) is None and not (tmp_path / "draft.json").exists()


def test_explain_describes_graphics_captions_layout_and_hook():
    before = _plan(hook=Hook(candidates=[HookCandidate(start=5, end=7, text="w5 w6", score=0.9),
                                         HookCandidate(start=8, end=9, text="w8", score=0.5)]))
    after = before.model_copy(deep=True)
    after.segments = [Segment(start=5, end=7, reason="hook"), Segment(start=0, end=20)]
    after.transcript.words[3].text = "Ka'Chava"
    edit.set_layout(after, 10, 12, "split")
    after.hook.chosen = 1
    lines = diff.explain(before, after)
    assert "Opens with “w5 w6”" in lines
    assert "Caption “w3” now reads “Ka'Chava”" in lines
    assert "Added a layout change (split) at 0:12.0-0:14.0" in lines
    assert any(line.startswith("Picked hook 2") for line in lines)
    assert lines[-1] == "Reel is now 22.0 s (+2.0 s)"
    assert diff.explain(before, before) == []


def test_first_cut_explains_silence_fillers_and_trims():
    words = [Word(text="Hello", start=0, end=0.5), Word(text="um", start=1.0, end=1.3),
             Word(text="world.", start=1.5, end=2.0), Word(text="Tangent", start=5.0, end=5.5),
             Word(text="here.", start=5.6, end=6.0), Word(text="Back", start=8.0, end=8.5)]
    plan = EditPlan(source=SOURCE, transcript=Transcript(words=words),
                    segments=[Segment(start=0, end=0.9), Segment(start=1.4, end=2.2), Segment(start=7.8, end=8.6)],
                    graphics=[Graphic(id="g1", type="kinetic_text", start=8, end=8.5, props={"text": "BACK"})])
    out = explain.first_cut(plan)
    kinds = [i["kind"] for i in out["items"]]
    assert kinds == ["filler", "trim", "graphic"]
    assert out["items"][0]["text"] == "Removed the filler “um” (0.5 s)." and out["items"][0]["at"] == 0.9
    assert "Left out “Tangent here.”" in out["items"][1]["text"]
    assert "where the speaker says “Back”" in out["items"][2]["text"]
    assert out["summary"].startswith("Cut 1 filler words, 5.6 s of off-topic speech.")
