# HyperCut architecture

HyperCut turns raw footage of one speaker (up to 3 minutes) into a vertical short: word-timed
captions, the strongest line moved to the start, motion graphics where the content calls for them,
silences and filler words cut, and the speaker kept centered in a 9:16 crop. The user steers the look
with a style prompt ("bold yellow captions, punchy, lots of zooms").

## The one idea that holds it together

Every stage reads or writes a single JSON document, the **edit plan** (`hypercut/plan.py`,
`schema/edit_plan.schema.json`). Analysis produces a plan; rendering consumes it. Claude decides
*what* should happen (which line is the hook, where a stat card goes), and deterministic code decides
*how* it looks. Claude never touches pixels, so the speaker is never altered, the same plan always
renders the same video, and a user can tweak the plan and re-render without re-running any AI.
See [ADR 0001](decisions/0001-edit-plan-is-the-contract.md).

## Pipeline

```
 upload (media/<job>/input.*)
    │
    ▼
 1. ingest ──────────► normalized.mp4 (constant frame rate), audio.wav (16 kHz mono), Source
    │
    ├──────────────► 2. transcribe ──► Transcript (word timings)  ──┐
    │                                                               │
    ├──────────────► 5. reframe ─────► Reframe (face track keys) ───┤
    │                                                               ▼
 style prompt ─► 3. style ─► Style ────────────────────────► 4. analyze ──► hook, segments,
                                                                            graphics, zooms
                                                                               │
                                       plan.json  ◄──────── assembled EditPlan ┘
                                           │
                                           ▼
                                    6. render (Remotion) ──► output.mp4 + captions.srt
```

Ingest runs first; transcription and reframing then run in parallel (one is audio, the other video).
Style runs as soon as the prompt arrives. Analysis needs the transcript and the style. Render needs the
finished plan.

| # | stage | module | input | output | tools |
|---|---|---|---|---|---|
| 1 | ingest | `hypercut/ingest` | any video | `normalized.mp4`, `audio.wav`, `Source` | FFmpeg / ffprobe |
| 2 | transcribe | `hypercut/transcribe` | `audio.wav` | `Transcript`, `captions.srt` | faster-whisper (local, default) or Deepgram |
| 3 | style | `hypercut/style` | prompt text | `Style` | presets + Claude |
| 4 | analyze | `hypercut/analyze` | transcript + style | `hook`, `segments`, `graphics`, `zooms` | Claude + FFmpeg loudness |
| 5 | reframe | `hypercut/reframe` | `normalized.mp4` | `Reframe` | MediaPipe face detection |
| 6 | render | `render/` | `plan.json` + video | `output.mp4` | Remotion (React, TypeScript) |

The API (`api/`, FastAPI) runs these stages as a job per upload and stores everything under
`media/<job_id>/`. The web app (`web/`, Next.js) uploads, shows the hook candidates, takes the style
prompt, previews the plan with the same Remotion components the renderer uses, and downloads the result.

## Time: one timeline for everything

All times in the plan are seconds on the **source** video. `segments` lists the pieces of source to keep,
in play order. The renderer walks the segments and maps each source time to output time; a caption word or
graphic whose span falls in a cut is simply not shown, and one that crosses a cut is clipped.

That is what makes the hook work without special cases. A cold open is just the hook span listed twice:
once first (`reason: "hook"`) and again in its original place. Cutting a pause is just ending one segment
and starting the next after it. Analyzers never need to know what else has been cut.

## Stage details

**Ingest.** `ingest(input_path, job_dir) -> (Source, normalized_mp4, audio_wav)`. `ffprobe` reads size, rate
and duration; inputs without video or audio, under 10 seconds or over 3 minutes are rejected with an
`IngestError` carrying a clear message (ADR 0102). FFmpeg re-encodes to 30 fps constant frame rate H.264/AAC
(variable frame rate phone footage breaks frame-accurate rendering) and extracts 16 kHz mono audio for
transcription (ADR 0101). `Source` is probed from the normalized file. Manual run:
`python -m hypercut.ingest <file> <out_dir>`.

**Transcribe.** Returns every word with start and end times. faster-whisper runs locally for free (the
`small` model handles 3 minutes in about a minute on CPU); Deepgram is the fast paid option, chosen with
`HYPERCUT_TRANSCRIBE=deepgram` and `DEEPGRAM_API_KEY`. Also writes an SRT for platforms that want one.
Entry point: `transcribe(wav_path, backend=None) -> Transcript`; `to_srt(transcript)` groups words into short
lines; `python -m hypercut.transcribe audio.wav --out transcript.json --srt captions.srt` runs it by hand.
The Whisper model comes from `HYPERCUT_WHISPER_MODEL` (default `small`). Both backends go through one cleanup
step so word timings are always ordered with `end > start`. See [ADR 0201](decisions/0201-backend-selection-and-word-cleanup.md)
and [ADR 0202](decisions/0202-srt-line-grouping.md).

**Style.** Six named presets (for example `bold_creator`, `clean_corporate`, `playful`, `cinematic`,
`minimal`, `podcast`) give a good result with an empty prompt. A prompt is turned into a `Style` by Claude,
starting from the closest preset and changing only what the prompt asks for, then validated against the
schema so a bad answer can never reach the renderer. Claude answers `{"preset", "changes"}`; the changes
are deep-merged onto the preset. Invalid output is retried once, then the preset is used as is. An empty
prompt returns `bold_creator` with no Claude call. API: `get_preset(name)`, `style_from_prompt(prompt)`,
CLI `python -m hypercut.style "prompt"` (see decision 0301).

**Analyze.** One Claude call reads the timed transcript and the style and returns, as JSON:
- up to three hook candidates, each a span with a score and a reason (bold claim, surprising number,
  question, conflict, payoff tease);
- filler words and dead air to cut (also detected deterministically from word gaps and FFmpeg
  `silencedetect`, so cuts don't depend on the model alone);
- graphics: each a span, a template type (`kinetic_text`, `stat_card`, `emoji_burst`, `list_build`,
  `lower_third`, `progress_bar`) and its props, with density capped by the style;
- punch-in zooms on emphasis and topic changes.

Code then assembles `segments` from the chosen hook strategy and the cuts.

**Reframe.** `reframe(video, source)` samples ~5 frames/s with OpenCV and takes the largest MediaPipe face per
frame. The track is smoothed (exponential, with a dead zone so the crop ignores small movements), clamped so the
full-height 9:16 window stays inside the frame, and stored as normalized crop-center keyframes (`cy` is always
0.5). No face, or an already-vertical source, means empty keys (center crop). The detector is an injectable
function so tests need no mediapipe. The renderer also uses the track to keep graphics off the face. See
decision 0501.

**Render.** A Remotion composition (`HyperCut`, props `{plan, videoSrc}`) draws, per output frame: the
cropped and zoomed source frame, the caption line for the current words (styled and animated by
`Style.caption`), and any active graphic templates. Output is 1080x1920, 30 fps H.264, with size, fps and
length taken from the plan. The video layer is one Remotion sequence per segment; overlays are driven by the
*source* time of the current frame, so the cold-open hook shows its captions and graphics both times it plays
and cut material shows nothing. The logic is in pure, unit-tested modules (`timing.ts`, `layout.ts`,
`captions.ts`). Crop follows the interpolated reframe keys (center crop without them); zooms scale about the
frame center; graphics take one of three vertical bands chosen to stay clear of the face and the captions.
Run it with `npm run render -- --plan plan.json --video normalized.mp4 --out out.mp4` in `render/`
(`REMOTION_BROWSER` selects a Chromium). See ADRs [0601](decisions/0601-render-architecture.md) to
[0604](decisions/0604-render-cli-and-browser.md).

## Claude calls

All of them go through `hypercut/llm.py`'s `ask_json`. By default it runs Claude Code headless
(`claude -p --output-format json`) on the user's own subscription; `HYPERCUT_LLM=api` switches to the
Anthropic API for when other people use the app. Every answer is parsed and validated with the pydantic
models before use. See [ADR 0003](decisions/0003-claude-via-subscription.md).

## Where things live

```
hypercut/        Python pipeline (one package per stage) + plan.py, llm.py
schema/          generated JSON schema + example plan
render/          Remotion project (TypeScript)
api/             FastAPI job server
web/             Next.js app
media/           uploads and outputs, git-ignored
docs/            this file and the decision records
```

## Cost

For personal use on a Claude subscription with local Whisper: nothing beyond the plan. With paid APIs,
about $0.05 to $0.15 of Claude and about $0.013 of Deepgram per 3-minute video.
