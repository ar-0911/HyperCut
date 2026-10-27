"""The edit-quality benchmark: run HyperCut on a folder of real videos and score every result (ADR 0023).

    python -m hypercut.bench BENCH_DIR [--out DIR] [--render] [--compare OLD/report.json]
    python -m hypercut.bench --jobs media/          # how much people corrected HyperCut's first cuts

BENCH_DIR holds source videos and, optionally, `<video name>.json` next to each with what a person decided:
    {"style": "style prompt to use", "transcript": "what is actually said", "hook": "the line that should open it"}

For each video: the whole pipeline runs (and the render, with --render), then automatic scores are written to
report.json and report.md: plan checks (hypercut.checks), caption word error rate against the reference
transcript, whether the chosen hook matches the expected one, pacing (pauses left, how much was kept), graphics,
per-stage time, and the export validation (hypercut.qa) when rendered. --compare flags regressions against an
earlier report, so a prompt change that helps hooks but breaks captions shows up.

Correction effort (--jobs): from each project's version history, how many versions and changes the user made
after the first cut and over how long. The number to drive down.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from hypercut import checks, edit, history
from hypercut import plan as plan_mod
from hypercut.plan import EditPlan

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
# Regressions worth failing a comparison on.
WER_SLACK = 0.02
HOOK_SLACK = 0.1


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def wer(reference: str, hypothesis: str) -> float:
    """Word error rate: word edits (substitute, insert, delete) to turn the hypothesis into the reference, per
    reference word."""
    ref, hyp = _tokens(reference), _tokens(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1] / len(ref)


def overlap(a: str, b: str) -> float:
    """How much two lines share, 0..1 (Jaccard of their words)."""
    x, y = set(_tokens(a)), set(_tokens(b))
    return len(x & y) / len(x | y) if x | y else 1.0


def score(plan: EditPlan, expected: dict | None = None, job_dir: Path | None = None) -> dict:
    """Automatic scores of one finished plan."""
    expected = expected or {}
    issues = checks.check(plan, job_dir)
    by_code: dict[str, int] = {}
    for i in issues:
        by_code[i.code] = by_code.get(i.code, 0) + 1
    reel = edit.reel_duration(plan)
    words = edit.reel_words(plan)
    gaps = [b.start - a.end for a, b in zip(words, words[1:]) if a.piece == b.piece and b.start > a.end]
    out = {
        "reel_seconds": round(reel, 2),
        "kept_fraction": round(reel / plan.source.duration, 3) if plan.source.duration else None,
        "fails": sum(i.severity == "fail" for i in issues),
        "warnings": sum(i.severity == "warn" for i in issues),
        "issues": by_code,
        "pauses_left": len(edit.pauses(plan)),
        "mean_gap": round(sum(gaps) / len(gaps), 3) if gaps else 0.0,
        "graphics": len(plan.graphics),
        "words_per_second": round(len(words) / reel, 2) if reel else 0.0,
    }
    hook = plan.hook.candidates[plan.hook.chosen].text if plan.hook.candidates else ""
    out["hook"] = hook
    if expected.get("hook"):
        out["hook_match"] = round(overlap(expected["hook"], hook), 3)
    if expected.get("transcript"):
        out["wer"] = round(wer(expected["transcript"], " ".join(w.text for w in plan.transcript.words)), 4)
    return out


def correction(job_dir: str | Path) -> dict | None:
    """How much a person changed HyperCut's first cut: versions saved after it, changes, and minutes spent
    between the first cut and the last saved version. None for a project with no history."""
    index = history._read_index(Path(job_dir))
    if not index.versions:
        return None
    first = next((v for v in index.versions if v.kind == "pipeline"), index.versions[0])
    later = [v for v in index.versions if v.created > first.created and v.kind not in ("pipeline", "render")]
    return {
        "versions": len(later),
        "changes": sum(len(v.changes) for v in later),
        "assistant_edits": sum(v.kind == "assistant" for v in later),
        "minutes": round((max(v.created for v in later) - first.created) / 60, 1) if later else 0.0,
    }


def compare(old: dict, new: dict) -> list[str]:
    """Regressions from an earlier report to this one, per video."""
    out = []
    before = {r["video"]: r for r in old.get("results", [])}
    for r in new.get("results", []):
        o = before.get(r["video"])
        if not o or "error" in r or "error" in o:
            if o and "error" in r and "error" not in o:
                out.append(f"{r['video']}: now fails to run ({r['error'][:80]})")
            continue
        a, b = o["scores"], r["scores"]
        if b["fails"] > a["fails"]:
            out.append(f"{r['video']}: {b['fails'] - a['fails']} more failed checks ({', '.join(b['issues'])})")
        if "wer" in a and "wer" in b and b["wer"] > a["wer"] + WER_SLACK:
            out.append(f"{r['video']}: caption error rate {a['wer']:.1%} -> {b['wer']:.1%}")
        if "hook_match" in a and "hook_match" in b and b["hook_match"] < a["hook_match"] - HOOK_SLACK:
            out.append(f"{r['video']}: hook match {a['hook_match']:.2f} -> {b['hook_match']:.2f}")
        qa_a, qa_b = (o.get("qa") or {}).get("ok"), (r.get("qa") or {}).get("ok")
        if qa_a and qa_b is False:
            out.append(f"{r['video']}: the export now fails validation")
    return out


def run_one(video: Path, out_dir: Path, expected: dict, render: bool, pipeline=None) -> dict:
    from hypercut import qa, run

    pipeline = pipeline or run.run_pipeline
    stages: dict[str, float] = {}
    clock = {"name": None, "t": time.time()}

    def on_stage(name: str) -> None:
        now = time.time()
        if clock["name"]:
            stages[clock["name"]] = round(now - clock["t"], 1)
        clock.update(name=name, t=now)

    record: dict = {"video": video.name}
    try:
        plan = pipeline(video, out_dir, expected.get("style", ""), on_stage=on_stage)
        on_stage("done")
        record["seconds"] = stages
        record["scores"] = score(plan, expected, out_dir)
        if render:
            t = time.time()
            run.render_plan(out_dir)
            stages["render"] = round(time.time() - t, 1)
            record["qa"] = qa.validate_job(out_dir)
    except Exception as e:  # one broken video must not stop the benchmark
        record["error"] = str(e)[:500]
    return record


def markdown(report: dict) -> str:
    lines = [f"# HyperCut benchmark, {time.strftime('%Y-%m-%d %H:%M', time.localtime(report['created']))}", "",
             "| video | reel s | fails | warnings | pauses left | hook match | WER | graphics | export |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in report["results"]:
        if "error" in r:
            lines.append(f"| {r['video']} | error: {r['error'][:60]} |||||||| ")
            continue
        s = r["scores"]
        qa_ok = (r.get("qa") or {}).get("ok")
        lines.append(f"| {r['video']} | {s['reel_seconds']} | {s['fails']} | {s['warnings']} | {s['pauses_left']} | "
                     f"{s.get('hook_match', '-')} | {s.get('wer', '-')} | {s['graphics']} | "
                     f"{'-' if qa_ok is None else 'ok' if qa_ok else 'FAIL'} |")
    if report.get("regressions") is not None:
        lines += ["", "## Regressions", ""] + ([f"- {x}" for x in report["regressions"]] or ["None."])
    return "\n".join(lines) + "\n"


def benchmark(bench_dir: Path, out: Path, render: bool = False, compare_to: Path | None = None, pipeline=None) -> dict:
    videos = sorted(p for p in bench_dir.iterdir() if p.suffix.lower() in VIDEO_EXT)
    results = []
    for v in videos:
        side = v.with_suffix(".json")
        expected = json.loads(side.read_text()) if side.is_file() else {}
        results.append(run_one(v, out / v.stem, expected, render, pipeline))
    report = {"created": time.time(), "bench": str(bench_dir), "results": results}
    if compare_to is not None:
        report["regressions"] = compare(json.loads(Path(compare_to).read_text()), report)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (out / "report.md").write_text(markdown(report))
    return report


def corrections(media: Path) -> dict:
    rows = []
    for d in sorted(p for p in media.iterdir() if p.is_dir()):
        c = correction(d)
        if c is not None:
            rows.append({"job": d.name, **c})
    edited = [r for r in rows if r["versions"]]
    return {
        "projects": len(rows),
        "kept_as_is": len(rows) - len(edited),
        "median_minutes": sorted(r["minutes"] for r in edited)[len(edited) // 2] if edited else 0.0,
        "mean_changes": round(sum(r["changes"] for r in edited) / len(edited), 1) if edited else 0.0,
        "jobs": rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hypercut.bench", description=__doc__.splitlines()[0])
    ap.add_argument("bench_dir", nargs="?")
    ap.add_argument("--out", help="where to write the runs and report (default BENCH_DIR/runs-<time>)")
    ap.add_argument("--render", action="store_true", help="also render and validate each export (slow)")
    ap.add_argument("--compare", help="an earlier report.json to check for regressions")
    ap.add_argument("--jobs", help="summarize correction effort across the projects in this media folder")
    args = ap.parse_args(argv)
    if args.jobs:
        print(json.dumps(corrections(Path(args.jobs)), indent=2))
        return 0
    if not args.bench_dir:
        ap.error("give a BENCH_DIR or --jobs")
    bench = Path(args.bench_dir)
    out = Path(args.out) if args.out else bench / time.strftime("runs-%Y%m%d-%H%M%S")
    report = benchmark(bench, out, args.render, Path(args.compare) if args.compare else None)
    print(markdown(report))
    return 1 if report.get("regressions") else 0


if __name__ == "__main__":
    sys.exit(main())
