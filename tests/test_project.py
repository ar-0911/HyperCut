import json
import zipfile
from pathlib import Path

import pytest

from hypercut import history, project
from hypercut import plan as plan_mod
from hypercut.ingest import manifest
from hypercut.plan import EditPlan, Source, Transcript, Word


def _job(tmp_path, footage=b"video"):
    job = tmp_path / "job"
    job.mkdir()
    (job / "normalized.mp4").write_bytes(footage)
    (job / "audio.wav").write_bytes(b"wav")
    (job / "brand-0123.png").write_bytes(b"png")
    (job / "frames").mkdir()
    (job / "frames" / "f1.jpg").write_bytes(b"jpg")
    original = tmp_path / "talk.mov"
    original.write_bytes(b"the original")
    manifest.save(job, {"original": {"name": "talk.mov", "bytes": original.stat().st_size, "sha256": manifest.sha256(original)},
                        "warnings": [], "stages": {}})
    plan = EditPlan(source=Source(path=str(job / "normalized.mp4"), width=1920, height=1080, fps=30, duration=10),
                    transcript=Transcript(words=[Word(text="hi", start=0, end=1)]))
    history.commit(job, plan, "pipeline")
    plan.transcript.words[0].text = "Hi"
    history.commit(job, plan, "edit", label="Mine")
    return job, original


def test_round_trip_with_footage(tmp_path):
    job, _ = _job(tmp_path)
    out = project.pack(job, tmp_path / "p.hypercut", job={"filename": "talk.mov"})
    names = zipfile.ZipFile(out).namelist()
    assert "normalized.mp4" in names and "brand-0123.png" in names and "history/v0002.json" in names
    assert not any(n.startswith("frames") for n in names)
    new = tmp_path / "opened"
    meta = project.unpack(out, new)
    assert meta["job"] == {"filename": "talk.mov"} and meta["footage"]
    plan = plan_mod.load(new / "plan.json")
    assert plan.source.path == str(new / "normalized.mp4") and plan.transcript.words[0].text == "Hi"
    versions = history.listing(new)["versions"]
    assert len(versions) == 2 and versions[0]["label"] == "Mine"
    assert json.loads((new / "history" / "v0001.json").read_text())["source"]["path"] == str(new / "normalized.mp4")


def test_without_footage_needs_the_same_original(tmp_path):
    job, original = _job(tmp_path)
    out = project.pack(job, tmp_path / "p.hypercut", footage=False)
    assert "normalized.mp4" not in zipfile.ZipFile(out).namelist()
    with pytest.raises(project.ProjectError, match="without its footage"):
        project.unpack(out, tmp_path / "a")
    other = tmp_path / "other.mov"
    other.write_bytes(b"something else")
    with pytest.raises(project.ProjectError, match="not the one"):
        project.unpack(out, tmp_path / "b", other)

    made = []

    def ingest(src, job_dir):
        made.append(Path(src).name)
        (Path(job_dir) / "normalized.mp4").write_bytes(b"video")
        manifest.save(job_dir, {"stages": {"ingest": {"status": "done"}}})

    project.unpack(out, tmp_path / "c", original, ingest=ingest)
    assert made == ["talk.mov"] and (tmp_path / "c" / "normalized.mp4").is_file()
    assert manifest.load(tmp_path / "c")["original"]["name"] == "talk.mov"  # the project's facts are kept


def test_a_moved_original_is_found_by_its_hash(tmp_path):
    job, original = _job(tmp_path)
    moved = tmp_path / "elsewhere" / "deep"
    moved.mkdir(parents=True)
    (moved / "decoy.mov").write_bytes(b"the 0riginal")  # same size, different bytes
    target = moved / "renamed.mov"
    original.rename(target)
    found = project.find_source(manifest.load(job)["original"], [tmp_path / "elsewhere"])
    assert found == target


def test_rejects_files_that_are_not_projects_or_escape(tmp_path):
    bad = tmp_path / "bad.hypercut"
    bad.write_bytes(b"nope")
    with pytest.raises(project.ProjectError, match="not a HyperCut project"):
        project.read_meta(bad)
    evil = tmp_path / "evil.hypercut"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr(project.PROJECT_FILE, json.dumps({"format": project.FORMAT, "version": 1}))
        z.writestr("../escape.txt", "x")
    with pytest.raises(project.ProjectError, match="outside"):
        project.unpack(evil, tmp_path / "e")
    assert not (tmp_path / "escape.txt").exists()
    newer = tmp_path / "newer.hypercut"
    with zipfile.ZipFile(newer, "w") as z:
        z.writestr(project.PROJECT_FILE, json.dumps({"format": project.FORMAT, "version": 99}))
    with pytest.raises(project.ProjectError, match="newer"):
        project.read_meta(newer)
