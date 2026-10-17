# 0001: The edit plan is the contract; Claude never edits pixels

Status: accepted, 2026-10-17

**Decision.** Every stage communicates only through the edit plan (`hypercut/plan.py`). Claude's output is
JSON that fills parts of the plan; rendering is deterministic code that reads it. All times are seconds on
the source timeline.

**Alternatives.** Letting a generative video model apply effects directly; passing ad-hoc files between
stages; storing times on the output timeline.

**Why.** The speaker must stay exactly as filmed, and generative video models re-create frames and can
subtly change faces. A typed plan makes results reproducible, lets users edit and re-render cheaply, lets
each stage be built and tested alone (which is what lets braid build them in parallel), and source-time
values never go stale when cuts change.

**Consequences.** Schema changes touch every stage, so they must be additive and come with an updated
example plan and regenerated `schema/edit_plan.schema.json`.
