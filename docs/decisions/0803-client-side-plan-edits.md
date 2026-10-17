# 0803: Web: hook choice and transcript edits happen in the browser

Status: accepted, 2026-10-17

**Decision.**
- The editor holds the edit plan in state. Picking a hook candidate sets `hook.chosen` and rebuilds `segments`
  with `chooseHook` (`web/lib/rehook.ts`), a port of `build_segments`: cold open puts the hook first and then the
  whole body, trim starts the body at the hook. The filler/silence cuts are not in the plan, so they are recovered
  from the gaps between existing body segments and reapplied. A toggle switches strategy the same way.
- Transcript editing changes only word text; timings stay. Captions update in the live preview immediately.
- Changes are saved with `PUT /jobs/{id}/plan` (Save, or automatically before Render). The API validates the plan.
- Graphics and zooms are not re-planned when the hook changes; they keep their source times.

**Alternatives.** A new API endpoint that re-runs `build_segments` (exact, but needs the original cuts stored and
a change in `api/`/`analyze`). Re-running analyze (slow and spends Claude calls). Editing word timings
(needs a waveform UI; out of scope).

**Consequences.** If a job was first made with `trim`, the part before the hook is not in the plan, so switching
to cold open afterwards has no cuts to recover there, and cuts before the hook are lost. Changing the hook is fully
exact for cold-open jobs, the default. A plan field storing the cut list would remove this limit.
