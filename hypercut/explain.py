"""Why the first cut looks the way it does, one line per decision (ADR 0021).

    first_cut(plan) -> {"summary": "...", "items": [{"at": reel s, "kind": "silence", "text": "Removed 1.2 s of silence"}, ...]}

Worked out from the plan itself (word timings, segments, hook, graphics), so it is true of any plan, even one
made before this module existed, and costs no Claude call. The editor lists the items; clicking one jumps
the playhead there.
"""

from __future__ import annotations

from hypercut import diff, edit
from hypercut.analyze.cuts import is_filler
from hypercut.plan import EditPlan

EPS = 1e-3
QUOTE = 8  # words quoted at most
LISTED_SILENCE = 0.5  # shorter pauses are only counted in the summary, not listed one by one


def _quote(words: list[str]) -> str:
    text = " ".join(words[:QUOTE]) + ("…" if len(words) > QUOTE else "")
    return f"“{text}”"


def first_cut(plan: EditPlan, index=None) -> dict:
    """`index`: the footage's visual index (`hypercut.vision`), when there is one, for what was decided from the picture."""
    items: list[dict] = []
    words = sorted(plan.transcript.words, key=lambda w: w.start)
    words_in = lambda a, b: [w for w in words if a - EPS <= (w.start + w.end) / 2 < b + EPS]  # noqa: E731

    hook_segs = [s for s in plan.segments if s.reason == "hook"]
    body = sorted((s for s in plan.segments if s.reason == "body"), key=lambda s: s.start)
    candidate = plan.hook.candidates[plan.hook.chosen] if plan.hook.candidates else None
    if hook_segs:
        said = [w.text for w in words_in(hook_segs[0].start, hook_segs[-1].end)]
        why = f": {candidate.why.rstrip('.')}" if candidate and candidate.why else ""
        items.append({"at": 0.0, "kind": "hook", "text": f"Opens with {_quote(said)} as a cold open{why}."})
    elif candidate and body and body[0].start > 1.0:
        why = f": {candidate.why.rstrip('.')}" if candidate.why else ""
        items.append({"at": 0.0, "kind": "hook",
                      "text": f"Starts at {_quote([w.text for w in words_in(body[0].start, candidate.end)])}, "
                              f"skipping the first {body[0].start:.1f} s{why}."})

    silence = fillers = trimmed = 0.0
    n_silence = n_filler = 0
    if body:
        edges = [(0.0, body[0].start)] + [(a.end, b.start) for a, b in zip(body, body[1:])]
        for i, (a, b) in enumerate(edges):
            if b - a <= 0.04:
                continue
            gone = words_in(a, b)
            at = edit.to_reel(plan, a - EPS if i else b)
            at = at[-1] if at else 0.0
            if i == 0 and (hook_segs or candidate):
                continue  # covered by the hook line
            if not gone:
                silence += b - a
                n_silence += 1
                if b - a >= LISTED_SILENCE:
                    items.append({"at": round(at, 2), "kind": "silence", "text": f"Removed {b - a:.1f} s of silence."})
            elif all(is_filler(w.text) for w in gone):
                fillers += b - a
                n_filler += len(gone)
                items.append({"at": round(at, 2), "kind": "filler",
                              "text": f"Removed the filler {_quote([w.text for w in gone])} ({b - a:.1f} s)."})
            else:
                trimmed += b - a
                items.append({"at": round(at, 2), "kind": "trim",
                              "text": f"Left out {_quote([w.text for w in gone])} ({b - a:.1f} s)."})
        tail = words_in(body[-1].end, plan.source.duration)
        if tail and not all(is_filler(w.text) for w in tail):
            last = words_in(body[-1].start, body[-1].end)
            items.append({"at": round(edit.reel_duration(plan), 2), "kind": "ending",
                          "text": f"Ends on {_quote([w.text for w in last[-QUOTE:]])} at the end of a sentence, "
                                  f"leaving out the last {plan.source.duration - body[-1].end:.1f} s."})

    for g in sorted(plan.graphics, key=lambda g: g.start):
        r = edit.first_reel(plan, g.start, g.end)
        if r is None:
            continue
        said = [w.text for w in words_in(g.start, g.end)]
        name = diff.NAMES.get(g.type, g.type)
        because = f" where the speaker says {_quote(said)}" if said else ""
        items.append({"at": round(r[0], 2), "kind": "graphic", "id": g.id,
                      "text": f"Added {diff.article(name)}{diff.title_of(g)}{because or '.'}"})
    for z in plan.zooms:
        r = edit.first_reel(plan, z.start, z.end)
        if r:
            items.append({"at": round(r[0], 2), "kind": "zoom",
                          "text": f"Pushed in on the face ({z.scale:.2f}x) to keep the shot moving."})

    if index is not None:
        for c in index.corrections:
            hits = edit.to_reel(plan, c.t + 0.01)
            if hits:
                items.append({"at": round(hits[0], 2), "kind": "spelling",
                              "text": f"Spelled “{c.heard}” as “{c.written}”, the way it is written in the footage."})
        from hypercut.vision import showing_spans

        for a, b, shot in showing_spans(index):
            r = edit.first_reel(plan, a, b)
            if r and not any(g.start < b and g.end > a and g.type in edit.VISUAL_TYPES for g in plan.graphics):
                what = next((o.description for o in shot.observations if o.description), shot.scene_type)
                items.append({"at": round(r[0], 2), "kind": "footage",
                              "text": f"Kept the footage clear of graphics: it shows {what[0].lower() + what[1:].rstrip('.')}."})

    items.sort(key=lambda it: (it["at"], it["kind"] != "hook"))
    parts = []
    if n_silence:
        parts.append(f"{n_silence} pauses ({silence:.1f} s)")
    if n_filler:
        parts.append(f"{n_filler} filler words")
    if trimmed:
        parts.append(f"{trimmed:.1f} s of off-topic speech")
    summary = (f"Cut {', '.join(parts)}. " if parts else "") + (
        f"The reel runs {edit.reel_duration(plan):.1f} s from {plan.source.duration:.1f} s of footage, "
        f"with {len(plan.graphics)} graphics.")
    return {"summary": summary, "items": items}
