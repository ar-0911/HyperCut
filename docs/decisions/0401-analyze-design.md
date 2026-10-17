# 0401: Analyze: Claude proposes, code validates and cuts

Status: accepted, 2026-10-17

**Decision.**
- One `hypercut.llm.ask_json` call per video. The transcript goes in as one line per word
  (`index time word`), which is compact and lets Claude refer to hooks by word index instead of
  guessing timestamps. Claude returns up to 3 hooks, graphics (types from `plan.GraphicType`, with props)
  and zooms.
- Hook candidates are word-index spans. Code turns them into times and text from the transcript, so a
  hook can never contain words the speaker did not say. Candidates are sorted by score; `chosen` is 0.
- Filler words (`um`, `uh`, `er`, ...) and gaps longer than `style.pacing.max_silence` are cut by plain
  code from word timings. With `audio_wav`, FFmpeg `silencedetect` adds silences the transcript misses.
  A pad of up to 80 ms is kept around speech so cuts don't clip words. Pieces under 150 ms are dropped.
- Segments: `cold_open` emits the hook span first (reason `hook`, with the same cuts applied) and then the
  whole video from the start, so the hook plays twice (ADR 0006). `trim` starts the body at the hook.
- Density: the prompt states the cap and code enforces it. Graphics per minute: minimal 2, balanced 5,
  heavy 9; zooms per minute: none 0, low 2, medium 4, high 8 (at least 1 when not "none").
- Validation drops bad items instead of failing: wrong types, non-numbers, times outside the source,
  spans under 0.3 s, hooks over 10 s, unknown graphic types, overlapping zooms. Graphics are capped at 5 s
  (except `progress_bar`). An unusable answer still yields a plan with cuts and no hook.

**Alternatives.** Letting Claude choose cuts (non-deterministic, can drop words mid-sentence);
timestamps instead of word indices (Claude drifts by fractions of a second, making cuts land inside words);
one call per feature (3x the subscription usage for no gain).

**Consequences.** Hook text and boundaries are always word-aligned. Cuts are reproducible without Claude.
Caps are approximate (rounded per minute). Tuning lives in constants at the top of `analyze.py`/`cuts.py`.
A model that returns no valid hook leaves `segments` as a plain cut of the video.
