# HyperCut: agent guide

HyperCut turns raw talking-head footage (up to 3 minutes) into a 1080x1920 short: transcript,
animated captions, the hook moved to the start, motion graphics, face-tracked crop. The speaker's
pixels are never regenerated; everything is an overlay or a cut.

## The contract

`hypercut/plan.py` defines the **edit plan** (`EditPlan`). Every stage reads and/or writes it, and
nothing else crosses stage boundaries. All times are seconds on the SOURCE timeline; the renderer maps
them through `segments`. `schema/edit_plan.schema.json` is generated from it (`python -m hypercut.plan`)
and is what the TypeScript renderer and web app read. Change the schema only with a matching update to
`schema/examples/sample_plan.json` and the generated JSON schema, and keep it backward compatible.

## Stages and who owns what

| stage | owns | in | out |
|---|---|---|---|
| ingest | `hypercut/ingest/` | any video file | normalized CFR mp4 + 16 kHz mono wav + `Source` |
| transcribe | `hypercut/transcribe/` | wav | `Transcript` with word timings; SRT export. Backends: local faster-whisper (default), Deepgram (`DEEPGRAM_API_KEY`) |
| style | `hypercut/style/` | prompt text | `Style` (named presets + prompt-to-style via `hypercut.llm`) |
| analyze | `hypercut/analyze/` | transcript + style | `hook`, `segments` (cuts fillers/silence), `graphics`, `zooms` via `hypercut.llm` |
| reframe | `hypercut/reframe/` | normalized mp4 | `Reframe` keys (MediaPipe face track, smoothed) |
| render | `render/` (Remotion, TypeScript) | edit plan JSON + source video | final mp4 |
| api | `api/` (FastAPI) | uploads to local `media/` | runs the stages as a job, serves results |
| web | `web/` (Next.js) | api | upload, pick hook, style prompt, preview, download |

Shared code: `hypercut/plan.py` and `hypercut/llm.py`. Don't rewrite them inside a stage task; if one
needs a change, keep it small and additive.

## Conventions

- Python 3.10+, pydantic v2. Each stage exposes one plain function as its entry point (e.g.
  `transcribe(wav_path) -> Transcript`) plus a `python -m hypercut.<stage>` CLI for manual runs.
- All Claude calls go through `hypercut.llm.ask_json`. Default backend is the Claude Code CLI on the
  user's subscription; never hard-require an API key.
- Heavy dependencies are optional extras in `pyproject.toml`; import them inside functions so the test
  suite runs without them. Tests must not call Claude, Deepgram or download models: use fakes.
- Tests: `.venv/bin/python -m pytest -q` (or `python -m pytest -q`). The render stage adds its own
  `npm test` in `render/`.
- Uploads and outputs live under `media/` (git-ignored). No cloud storage yet.

## Documentation is part of the task

- `docs/architecture.md` explains how the system works; `docs/decisions/` records every design decision.
- When your task makes a real choice (a library, a format, a trade-off, a default), add a numbered decision
  record in `docs/decisions/` (what, alternatives, why, consequences) and update your stage's section of
  `docs/architecture.md`.
- Decision numbers are reserved per stage so parallel work never collides: ingest 0101+, transcribe 0201+,
  style 0301+, analyze 0401+, reframe 0501+, render 0601+, api 0701+, web 0801+. Shared or cross-cutting
  decisions use the next free number below 0100.
- In `docs/architecture.md`, edit only your stage's paragraph(s). Don't edit `docs/decisions/README.md`;
  the lead adds the index rows when the work lands.
