import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from hypercut import plan

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "schema" / "examples" / "sample_plan.json"


def test_sample_plan_loads():
    p = plan.load(SAMPLE)
    assert p.hook.candidates[1].score == 0.81
    assert p.output.height == 1920
    assert p.output_duration() == pytest.approx(2.0 + 2.4 + 6.1)


def test_roundtrip(tmp_path):
    p = plan.load(SAMPLE)
    out = tmp_path / "p.json"
    plan.save(p, out)
    assert plan.load(out) == p


def test_rejects_span_past_source_end():
    data = json.loads(SAMPLE.read_text())
    data["segments"].append({"start": 11.0, "end": 13.0})
    with pytest.raises(ValidationError):
        plan.EditPlan.model_validate(data)


def test_rejects_reversed_span():
    with pytest.raises(ValidationError):
        plan.Span(start=2.0, end=1.0)


def test_rejects_unknown_fields():
    data = json.loads(SAMPLE.read_text())
    data["surprise"] = True
    with pytest.raises(ValidationError):
        plan.EditPlan.model_validate(data)


def test_checked_in_schema_is_current():
    checked_in = json.loads((ROOT / "schema" / "edit_plan.schema.json").read_text())
    assert checked_in == plan.json_schema(), "run: python -m hypercut.plan"
