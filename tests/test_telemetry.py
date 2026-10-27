import json

from hypercut import telemetry


def test_off_until_turned_on(tmp_path):
    assert not telemetry.enabled(tmp_path)
    assert not telemetry.record(tmp_path, "render_done", seconds=10)
    assert not (tmp_path / telemetry.FILE).exists()
    telemetry.set_enabled(tmp_path, True)
    assert telemetry.record(tmp_path, "render_done", seconds=10)
    assert telemetry.summary(tmp_path)["counts"] == {"render_done": 1}


def test_only_listed_fields_and_values_are_kept(tmp_path):
    telemetry.set_enabled(tmp_path, True)
    telemetry.record(tmp_path, "job_created", mode="podcast", kit=True, filename="secret.mov",
                     style_prompt="make it like my ex's channel")
    telemetry.record(tmp_path, "job_created", mode="anything else", kit="yes")
    assert not telemetry.record(tmp_path, "transcript", text="hello")
    first, second = telemetry.events(tmp_path)
    assert {k: v for k, v in first.items() if k != "t"} == {"event": "job_created", "mode": "podcast", "kit": True}
    assert {k: v for k, v in second.items() if k != "t"} == {"event": "job_created"}
    raw = (tmp_path / telemetry.FILE).read_text()
    assert "secret" not in raw and "ex's" not in raw and "hello" not in raw


def test_summary_and_clear(tmp_path):
    telemetry.set_enabled(tmp_path, True)
    for seconds in (100, 200, 300):
        telemetry.record(tmp_path, "render_done", seconds=seconds)
    telemetry.record(tmp_path, "render_failed")
    for outcome in ("kept", "skipped"):
        telemetry.record(tmp_path, "suggestion", kind="hook", outcome=outcome)
    s = telemetry.summary(tmp_path)
    assert s["render_success"] == 0.75 and s["median_render_seconds"] == 200 and s["suggestion_kept"] == 0.5
    telemetry.clear(tmp_path)
    assert telemetry.summary(tmp_path)["events"] == 0
    assert json.loads((tmp_path / telemetry.SETTINGS).read_text())["telemetry"] is True
