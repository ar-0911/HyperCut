# 0023. Automatic quality: plan checks, export validation, a benchmark and a regression suite

Status: accepted (2026-10-26)

## What

Three layers, none of which calls Claude or a model:

1. **Plan checks** (`hypercut/checks.py`, `POST /jobs/{id}/checks`, `python -m hypercut.checks plan.json`):
   a word clipped by a cut (fail), a picture file missing from the project (fail), pauses the pacing should have
   removed, fillers still in, a reel outside 15-60 s, the reel ending mid-sentence, a hook over 12 s or starting
   mid-sentence, two full-frame visuals at once, a graphic on screen under 0.6 s or entirely in cut footage, and the
   same visual twice (warn). The editor re-runs them 0.8 s after each change and lists them in a Checks card;
   clicking one seeks there.
2. **Export validation** (`hypercut/qa.py`): after every render the API inspects `output.mp4` with ffprobe and
   FFmpeg filters and saves `output.qa.json`: audio present, size and frame rate as asked, length matches the
   plan (within a frame per piece), audio and video end together (fail); black frames outside the fades (fail);
   a frozen picture over 1 s, silent dropouts over 1.2 s, loudness away from -14 LUFS by more than 3 LU, true peak
   over -1 dBTP (warn). The job's `qa` field carries it; the editor shows it under "Last export". A clean render
   exit is no longer taken as a good file.
3. **Benchmark and regressions** (`hypercut/bench.py`): `python -m hypercut.bench BENCH_DIR` runs the pipeline
   (and with `--render`, the render and validation) on a folder of real videos, each optionally with a sidecar
   `<name>.json` holding the reference transcript, the expected hook and a style prompt, and writes `report.json`
   and `report.md`: checks, caption WER, hook match, pauses left, pacing, graphics, time per stage, export
   validation. `--compare old/report.json` lists regressions (more failed checks, WER up 2 points, hook match down
   0.1, an export that now fails) and exits non-zero. `--jobs media/` summarizes correction effort from version
   histories (ADR 0021): versions, changes and minutes after the first cut, the metric to drive down.
   `tests/fixtures/real_footage_plan.json` (the plan made for the 69 s test footage) is checked in every test run.

## Alternatives

- **Claude review only** (ADR 0019, frames of the render): catches taste problems but is slow, costs a call,
  and can't measure loudness, sync or length. It stays as the human-like layer on top.
- **Perceptual metrics (VMAF, SSIM) against a reference render.** Need a golden render per change and say little
  about edit quality; deterministic checks of the known failure modes are cheaper and explain themselves.
- **Normalizing loudness now.** The validator reports first; the render's loudness pass is P1 work, measured by
  this check. The v2 test reel already shows a +0.1 dBTP peak (clipping), the first thing it caught.

## Consequences

- Every render costs a few seconds more per minute of video for validation (it runs after the render slot is
  freed, so the next render isn't held up).
- Edit-quality changes can be judged on numbers over a benchmark set instead of watching a few videos; human
  ratings (hook quality, overall) still need a person and are recorded separately when we add them.
- The benchmark needs videos the user is happy to keep locally; none ship with the repo.
