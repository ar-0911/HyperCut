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
| 6 | render | `render/` | `plan.json` + video | `output.mp4`, loudness-normalized to -14 LUFS (ADR 0616) | Remotion (React, TypeScript), FFmpeg loudnorm |
| 7 | matte (only when asked) | `hypercut/matte` | `normalized.mp4` + reframe | `matte.webm` (speaker cut-out) | MediaPipe selfie segmentation + MODNet + FFmpeg |
| 8 | generate (only with keys) | `hypercut/generate` | plan with `generate` requests | `gen-*` stock and generated pictures / clips | Pexels, Pixabay, Wikimedia Commons; fal.ai or local diffusers |
| 9 | look (visual index) | `hypercut/vision` | `normalized.mp4` + reframe shots | `visual_index.json` (shots, frames, what is on screen), name respellings | FFmpeg, Tesseract if installed; Claude or Ollama only when chosen |

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

## Projects: versions, explanations, recovery

A job folder is a project. `plan.json` is the current edit; `history/` keeps every saved version (the first cut,
the user's saves, accepted assistant edits, going back) with who made it, an optional name and what changed in words;
`draft.json` is the editor's autosave of unsaved edits, offered back on reopening. Undo/redo between versions and
"go back to version N" survive a reload or a crash, and going back never deletes anything. On start, the server
marks work that was running when it stopped as interrupted, and a failed job can be retried. Every change is
explained from the plans themselves (`hypercut/diff.py`), the first cut has a "why" for each decision
(`hypercut/explain.py`), and assistant edits are proposals the user keeps or rejects after seeing before and after.
The assistant has word-accurate operations (remove a pause, tighten a stretch, cut exact words). See
[ADR 0021](decisions/0021-project-history-autosave-recovery.md) and
[ADR 0022](decisions/0022-explained-edits-and-word-accurate-ops.md).

A project travels as one `.hypercut` file (`hypercut/project.py`): the plan, every version, the transcript, the
visual index and manifest, the files the plan shows, and the footage unless it is left out. Opening one makes a
new job; a project without footage asks for the original, recognised by its SHA-256 even if it was moved or
renamed. See [ADR 0027](decisions/0027-portable-projects.md).

Editing goes on during a render: the render works from a snapshot (`render.plan.json`) and puts what it drew back
into the plan only if nobody edited meanwhile; the job says which version the download is. The editor previews a
960 px `proxy.mp4` instead of the full video. See [ADR 0028](decisions/0028-background-render-and-proxy-preview.md).

## Understanding the footage

Next to the transcript, the "look" stage (`hypercut/vision`) builds a visual index of the source: shots (the face
tracker's hard cuts or FFmpeg's scene score), one sampled frame per shot (more for long ones, 24 at most), text on
screen, and, if the user picks one, a description of each frame from a local vision model (Ollama) or Claude. The
index is evidence about the footage, kept in `visual_index.json` and out of the plan. The analyze prompt reads a line
per shot; shots that show a screen, a product or other footage are kept clear of drawn visuals; names written in
the footage fix what speech recognition misheard. Without it, everything works from the transcript alone. See
[ADR 0024](decisions/0024-visual-index.md).

## Editing modes

What the user is making (talking head, podcast clip, product demo, vlog) is `plan.style.mode`. A mode
(`hypercut/modes.py`) is a policy over the same engine: a patch of pacing, camera, graphics, caption and cut
settings applied over the style's preset (what the user asked for still wins), and a paragraph of planner guidance
on hooks, what to keep and which graphics suit it. It is picked on the upload page or switched later with the
assistant, which re-cuts the pauses and keeps the rest of the edit. See [ADR 0025](decisions/0025-editing-modes.md).

## Brand kits

A brand kit (`hypercut/brand.py`, stored by `api/kits.py` under `media/kits/`) is the look of a style (captions,
colours, cuts) plus a logo, music, an end card line and a font. Applying one copies its files into the job as
`brand-*` and records them in `plan.brand`; the renderer's `BrandLayer` puts the logo in its corner, loops the music
under the reel with ducking from the word timings, and shows the end card over the last seconds. Chosen at upload
or in the editor's Brand tab. See [ADR 0026](decisions/0026-brand-kits.md).

## Quality: checks, export validation, benchmark

Plan checks (`hypercut/checks.py`) find what a first watch would: clipped words, leftover pauses, a reel that ends
mid-sentence or runs outside 15-60 s, hooks that start mid-sentence, visuals fighting for the same moment, missing
picture files. The editor re-runs them on every change. After each render the API validates the file itself
(`hypercut/qa.py`: size, frame rate, length against the plan, audio/video sync, black and frozen frames, sound
dropouts, loudness and peaks) into `output.qa.json`. `python -m hypercut.bench` scores the whole pipeline on a
folder of real videos (checks, caption WER, hook match, pacing, export validation), compares against an earlier
run to catch regressions, and with `--jobs` measures how much people correct the first cut. See
[ADR 0023](decisions/0023-quality-checks-export-validation-benchmark.md).

## Stage details

**Ingest.** `ingest(input_path, job_dir) -> (Source, normalized_mp4, audio_wav)`. `ffprobe` reads size, rate
and duration; inputs without video, under 10 seconds or over 3 minutes are rejected with an
`IngestError` carrying a clear message (ADR 0102); a file without sound gets a silent track (ADR 0104). FFmpeg re-encodes to 30 fps constant frame rate H.264/AAC
(variable frame rate phone footage breaks frame-accurate rendering) and extracts 16 kHz mono audio for
transcription (ADR 0101). `Source` is probed from the normalized file. Manual run:
`python -m hypercut.ingest <file> <out_dir>`. Sources taller than 1920 pixels are scaled down to 1920 tall (decision 0103), since the 1080x1920 output never uses more.
Ingest also writes `manifest.json` (ADR 0104): the original's facts (SHA-256, codecs, rotation, orientation, frame
rate and whether it varies, HDR, audio tracks), warnings in plain words for what it had to fix, and each stage's
status, updated by the pipeline. The job page shows the warnings.

**Transcribe.** Returns every word with start and end times. faster-whisper runs locally for free (the
`small` model handles 3 minutes in about a minute on CPU); Deepgram is the fast paid option, chosen with
`HYPERCUT_TRANSCRIBE=deepgram` and `DEEPGRAM_API_KEY`. Also writes an SRT for platforms that want one.
Entry point: `transcribe(wav_path, backend=None) -> Transcript`; `to_srt(transcript)` groups words into short
lines; `python -m hypercut.transcribe audio.wav --out transcript.json --srt captions.srt` runs it by hand.
The Whisper backend reads ingest's wav itself and passes faster-whisper the samples, which sidesteps a
PyAV incompatibility (ADR 0203).
The Whisper model comes from `HYPERCUT_WHISPER_MODEL` (default `small`). Both backends go through one cleanup
step so word timings are always ordered with `end > start`. See [ADR 0201](decisions/0201-backend-selection-and-word-cleanup.md)
and [ADR 0202](decisions/0202-srt-line-grouping.md).

**Style.** Six named presets (for example `bold_creator`, `clean_corporate`, `playful`, `cinematic`,
`minimal`, `podcast`) give a good result with an empty prompt. A prompt is turned into a `Style` by Claude,
starting from the closest preset and changing only what the prompt asks for, then validated against the
schema so a bad answer can never reach the renderer. Claude answers `{"preset", "changes"}`; the changes
are deep-merged onto the preset. Invalid output is retried once, then the preset is used as is. An empty
prompt returns `bold_creator` with no Claude call. API: `get_preset(name)`, `style_from_prompt(prompt)`,
CLI `python -m hypercut.style "prompt"` (see decision 0301). `style.depth` (green-screen effects) is off in
every preset and only turned on when the prompt asks for something behind or around the speaker, a changed
background or a depth look; a keyword check overrules Claude if it turns it on for a prompt that never asked (decision 0901).
`style.depth.cutout` (the speaker cut out of the frame) is narrower still: only a prompt that names a different
background or something behind the speaker turns it on, with the same kind of keyword check; otherwise effects
are drawn over the real room and the background stays `original` (decision 0614).

**Analyze.** `analyze(transcript, source, style, audio_wav=None, strategy="cold_open")`. One Claude call
gets the transcript as `index time word` lines and the style, and returns as JSON:
- up to three hook candidates as word-index spans with a score and a reason (bold claim, surprising number,
  question, conflict, payoff tease); code converts them to times and text;
- graphics: each a span, a template type (`kinetic_text`, `stat_card`, `list_build`, `lower_third`,
  `progress_bar`) and its props, capped per minute by `style.graphics.density`;
- punch-in zooms on emphasis and topic changes, capped per minute by `style.camera.zoom_frequency`.

Every item is validated against the source duration and dropped if invalid. Cuts never involve Claude:
filler words and gaps over `style.pacing.max_silence` come from word timings (plus FFmpeg `silencedetect`
when the wav is given). Code then assembles `segments`: `cold_open` puts the hook first and keeps it in
place; `trim` starts at the hook. See ADR 0401. Each cut pause keeps `pacing.keep_pause` (0.15 s) on each side
and is only cut if at least 0.25 s goes, so there are no tiny jump cuts. The same call names the ending, the
last word worth keeping; code checks it ends a sentence in the second half (falling back to the last such word)
and ends the reel 0.4 s after it, so a reel never stops mid-thought. `recut(plan, wav)` rebuilds the segments
for new pacing and keeps the hook and ending (ADR 0403).

With `visuals=True` (the default in `run_pipeline`; `--no-visuals` turns it off) analyze also directs the
look of the video (`hypercut/analyze/visuals.py`, ADR 0402). Code groups the played words into beats of
2-4.5 s, breaking at sentence ends. One director call, allowed to search the web for reference, picks each
beat's `layout` mode (`speaker`, `split` with the visual above the speaker, or `visual` full frame) and
writes an art brief specific to what is said, or picks a text card. Parallel illustrator calls turn
the briefs into original SVG drawings. Code sanitizes them and splits each into layers that the renderer
reveals in order (graphic type `illustration`). Code also enforces the mix: no visual-only opening, no two
visual-only beats in a row, visual-only under 30% of the time. Text graphics from the main call that would
share the panel with a visual are dropped.

Big titles behind the speaker and `backgrounds` need the speaker cut out, so they are only asked for with
`style.depth.cutout` (decision 0614); without it the prompt says the real background stays as filmed. With
`style.depth.enabled` and `cutout` the same main call also returns a few big titles to place behind the speaker's
head (`kinetic_text` with `layer: "behind"`, ids `b1`..., about three a minute, only in speaker stretches)
and optional `backgrounds` stretches (blur or dim, never a plain colour or gradient, decision 0613) for emphasis (decision 0901), plus a few effects
around the speaker (`orbit`, `fly_out`, `particles`, ids `o1`..., only where a moment calls for one, at most
one a minute, with `style.depth.around`), capped in length, never overlapping, only in speaker stretches.
Orbit and fly-out items are drawn by Claude as small sticker SVGs (`visuals.draw_icons`, `props.art`), and
items added in the editor are drawn before the render (decision 0610). Analyze now proposes stage graphics
instead (`hypercut/analyze/stage.py`, decision 0611): `card_stack`, `scene` and `chart`, ids `s1`..., at most
two a minute and only where a moment calls for one; cards and scenes are drawn by the illustrator. They are
asked for in every reel (with `style.depth.around`, on by default): without the cut-out they are animated over
the real footage in the free space beside the speaker and there are no scenes (decision 0614).

The main call also picks a few full-screen motion graphics (`hypercut/analyze/motion.py`, decision 0612):
`"motion"` moments of 1.8-3.2 s, at most two a minute, each with a short title and the idea of the one thing
to show. They get the whole frame (layout `visual`, other visuals there cleared), and one more Claude call
designs each as a 3D scene in a small validated JSON scene language (shapes, finishes, moves, camera, a light
or dark studio). After reframe, `analyze/transitions.py` picks a few animated transitions (`plan.cuts`,
decision 0613): a drop where the cold open hands over to the story, and whip, zoom or push at hard cuts between
shots that land on the speaker alone, at most three a minute and 12 s apart. No Claude call. With editorial cuts
(`transitions.style: "editorial"`, the default, decision 0614) only the cold-open drop is added. Last,
`analyze/cutaways.py` stretches any visual (split panel, B-roll, motion graphic) whose edge is within 0.8 s of a
jump cut across it by 0.4 s, the way B-roll is laid over a jump cut, so the speaker never reappears for a few
frames and then jumps.

When the user asks for pictures (0020) and stock footage or generated pictures are set up (0016), the visual director may also pick `footage` (a stock search) or `picture` (a generation prompt) for a beat, plus one `look` line all pictures share; these become `media` graphics with a `generate` request and a brief to draw if nothing fits. Motion moments also ask for a generated clip, keeping their 3D scene as the fallback. See [ADR 0404](decisions/0404-sources-per-visual.md).

**Reframe.** `reframe(video, source)` samples ~5 frames/s with OpenCV and takes the largest MediaPipe face per
frame. The track is smoothed (exponential, with a dead zone so the crop ignores small movements), clamped so the
full-height 9:16 window stays inside the frame, and stored as normalized crop-center keyframes. `cy` is the
face's own height in the frame, smoothed the same way; the renderer zooms in on it and keeps graphics off it
(decision 0504). No face, or an already-vertical source, means empty keys (center crop). The detector is an injectable
function so tests need no mediapipe. Detection uses the MediaPipe Tasks face detector, whose model is fetched
once into `~/.cache/hypercut` (decision 0502). Hard cuts between shots are found from colour-histogram jumps
between samples, and at a cut the crop snaps to the new shot's speaker instead of easing (decision 0503), so
montages of several speakers stay framed. The renderer also uses the track to keep graphics off the face. See
decision 0501. Small faces in wide shots are found by also searching full-height square tiles of the frame,
cuts are checked on every frame, and in each shot the crop follows the face with the strongest track across
the shot rather than the biggest face-like thing in each frame (a shirt pattern, hands), with stray points
dropped by a running median; a shot with no face is centred (decision 0505). The hard cuts are also kept as
`reframe.shots` (source times), where animated transitions can go (decision 0613). In a shot with two or more
people (a podcast two-shot), the crop goes to whoever is talking: MediaPipe's face landmarker reads how open each
mouth is, the person whose jaw moves most over a second leads, and after 1.5 s in the lead the crop jumps to them
like a cut (`reframe.switches`, listed in "Why this cut"). Single-person footage never loads the landmarker
(decision 0506).

**Matte.** Only when the plan asks for the speaker cut out (`style.depth.enabled` and `style.depth.cutout`: a
different background or things behind the speaker, decision 0614), `matte(video, source,
reframe, out)` cuts the speaker out of every frame and writes `matte.webm`: VP9 with an alpha channel, frame
for frame with `normalized.mp4`, the speaker's own pixels where they are and transparent elsewhere. FFmpeg
decodes a 1280 px wide copy. Two MediaPipe selfie segmentation models see a 640 px copy of it (multi-class
for a clean silhouette, plain selfie for what the speaker holds); `refine` keeps only the person at the
reframe's main face, adds back held objects inside the silhouette's convex hull and averages with the previous
frame except across a cut. MODNet portrait matting (ONNX, optional) draws the hair and soft edges, limited to
that speaker and filled with MediaPipe's solid body (`with_hair`); a guided filter then snaps the edge to the
1280 px picture and a short opacity ramp trims the rim of old background (`snap_edge`). The alpha is piped
back to FFmpeg, which scales it up and merges it with the untouched full-size frames. About 12 s per second
of video on 4 CPUs with MODNet, 4 s without (no onnxruntime, or the model can't be downloaded). `run_pipeline`
starts it while analyze runs; the API makes it on demand when the editor turns the effects on, and a render
makes it if missing. Models come from storage.googleapis.com and huggingface.co into `~/.cache/hypercut`.
CLI `python -m hypercut.matte normalized.mp4 --plan plan.json`. See decisions 0901 and 0902.

**Render.** A Remotion composition (`HyperCut`, props `{plan, videoSrc}`) draws, per output frame: the
cropped and zoomed source frame, the caption line for the current words (styled and animated by
`Style.caption`; lines break by phrase, never on "the" or "of", never leaving a sentence's last word alone, and
within the characters that fit at the caption size, decision 0617), and any active graphic templates. Output is 1080x1920, 30 fps H.264, with size, fps and
length taken from the plan. The video layer is one Remotion sequence per segment; overlays are driven by the
*source* time of the current frame, so the cold-open hook shows its captions and graphics both times it plays
and cut material shows nothing. The logic is in pure, unit-tested modules (`timing.ts`, `layout.ts`,
`captions.ts`); `sceneAt(plan, t)` gives both layers the frame's layout mode, speaker panel, crop, zoom and
face point. `plan.layout` switches between three modes (decision 0605): `speaker` (full frame; the default),
`split` (speaker slides into the bottom half, visuals above on the studio set, captions on the seam) and `visual` (the visual graphic fills the frame while the speaker keeps talking underneath); a
split/visual span with no visual graphic on screen plays as speaker. Crop follows the interpolated reframe
keys (center crop without them); zooms scale about the face (`cx`, `cy` from the track, decision 0606);
in speaker mode graphics take one of three vertical bands chosen to stay clear of the face and the captions.
`illustration` graphics are Claude-drawn SVG layers that pop in one by one. Every frame is a pure function
of the frame number (no CSS animation, no randomness). `media` graphics are the user's own imported
pictures and clips (decision 0607): they fill the split panel or, in a `visual` span, the whole frame;
pictures drift in slowly, clips play muted from `trim_start` in one Remotion sequence per stretch of output
(`mediaRuns`, so B-roll plays straight through small filler cuts) and hold their last frame if the block
outlasts the clip. In the browser preview they load from the `assetBase` prop; in the final render they sit
next to the video. `pacing.speed` slows or speeds the whole reel (segments last `duration / speed`, video
plays at that rate, B-roll at normal speed). `transitions.style` is `editorial` (the default, `src/editorial.ts`,
decision 0614), `hard`, `smooth` (each segment overlaps the next by `length` and crossfades) or `zoom`
(alternate segments punched in). Editorial cuts join pieces the way an editor would: a J-cut at every jump cut
(the outgoing picture holds 4 frames, silent, while the next piece's sound starts; the kept pause keeps lips in
sync), pieces of the same shot alternate between normal and 1.12x framing about the face, and a new shot (a hard
cut in the source or a jump to another shot) settles in from 1.04x over 0.4 s; audio eases at every cut,
and `fade_in`/`fade_out` fade picture and sound at the ends. Caption fonts are twelve bundled Google fonts
(`src/fonts.ts`), and `caption.box` puts each line in a rounded box instead of an outline. See decisions 0608
and 0613. A few cuts are animated (`plan.cuts`, `src/cuts.ts`, decision 0613): for a few frames the last frame
before the cut, footage, graphics and captions together, is held (Remotion `Freeze`) and dropped, whipped,
pushed through or slid away over the live incoming footage. Backdrops are never a flat colour: split and
visual stretches, cards, charts and colour backgrounds stand on a studio set with a grid floor
(`src/Backdrop.tsx`). A `motion` graphic (`src/Motion.tsx`, decision 0612) fills the frame with a 3D scene
drawn by three.js through `@remotion/three` (software WebGL in the render): the scene is measured at rest
and fitted under its serif title, lit by three's built-in room environment, with sprung entrances and a slow
camera push, all pure functions of time. Green-screen effects (decision 0609) need the `matteSrc` prop (the
cut-out video): the video layer then draws the footage with its background kept, blurred, dimmed or covered
by the studio set (tinted with a colour if asked) or an imported picture/clip (`plan.backgrounds`, else `style.depth.background`, with optional
parallax drift), then graphics with `layer: "behind"` (big titles around the head, or any visual filling the
frame), then the cut-out speaker on top, then the usual overlays. The cut-out pass is only mounted on frames
that need it. Without a cut-out, or in split and visual stretches, behind graphics are placed in front like
any other graphic, off the face. Effects around the speaker (`orbit`, `fly_out`, `particles`, decision 0610)
are pure functions of time giving each element a depth: the far ones are drawn before the cut-out, the near
ones after it, and near ones fade out before they reach the face; without a cut-out all are drawn in front.
Items are the drawn stickers, or a built-in icon (`src/icons.ts`) when there is no drawing. Stage graphics
(`src/Stage.tsx`, decision 0611) are drawn in the behind layer: cards slide out from behind the speaker down
one side, a scene replaces the room, a chart builds over a studio backdrop; the cut-out is pulled back to 74%
about the bottom of the frame (and moved aside for cards). Without the cut-out (the default, decision 0614)
they are drawn over the real footage instead: cards slide in from the frame edge into the space beside the
face, sized to clear it, and a chart builds in the taller of the spaces above the face and between the face and
the captions; scenes are not drawn. The matte is only used with `style.depth.cutout`.
Run it with `npm run render -- --plan plan.json --video normalized.mp4 --out out.mp4 [--assets DIR] [--matte matte.webm]` in
`render/` (`REMOTION_BROWSER` selects a Chromium; imported files are read from the video's folder unless
`--assets` says otherwise). See ADRs [0601](decisions/0601-render-architecture.md) to
[0614](decisions/0614-real-background-and-editorial-cuts.md).


Pictures and clips (imported, stock or generated) fill the split panel or the frame; stills move (`props.move`: push in, pull out, pans, rise), a CC BY credit shows small in the corner, and a `media` graphic without `src` draws nothing yet. A motion graphic with `src` plays that generated clip under its title instead of the 3D scene. Text graphics may carry their own colour (`props.accent`). `render --overlays 1` (prop `overlaysOnly`) renders graphics and captions alone on transparency as ProRes 4444 for the editor export. See [ADR 0615](decisions/0615-stills-clips-credits-overlays.md).

**Generate.** `generate(plan, job_dir)` (`hypercut/generate/`, `python -m hypercut.generate JOB_DIR`) fills in every graphic whose `props.generate` asks for stock footage (`kind: stock`, `query`), a generated still (`image`, `prompt`) or a generated clip (`video`: a still, then image-to-video), saving `gen-<hash>.<ext>` in the job folder and setting `src` (plus `credit` for stock). Stock comes from Pexels, Pixabay and Wikimedia Commons (open licences only), with Claude looking at the thumbnails to pick the shot; generation from fal.ai (`FAL_KEY`) or open models on a local GPU (`HYPERCUT_GEN_LOCAL=1`). It runs after analyze, before each render and from the editor; results are cached by request and every paid call is checked against `HYPERCUT_GEN_BUDGET_USD` (default $2 a video, kept in `generate.json`). It is opt-in per video (the upload checkbox, `pictures` on `POST /jobs`, `--pictures`; [ADR 0020](decisions/0020-pictures-opt-in.md)); with it off, or no keys set, nothing is planned, offered or fetched and every visual is drawn. What can't be fetched becomes a drawing of its brief; a motion moment keeps its 3D scene. See [ADR 0016](decisions/0016-stock-and-generated-assets.md).

**Finishing tools.** `hypercut/variants.py`: other hooks (`rehook`) and 30 s / 45 s cuts ending on a full sentence (`trim_to`), each saved as its own job; recipes are saved styles in `media/recipes.json` ([ADR 0018](decisions/0018-recipes-and-variants.md)). `hypercut/review.py`: Claude looks at up to 16 frames of the render and proposes fixes as editor operations ([ADR 0019](decisions/0019-vision-review.md)). `hypercut/export.py`: FCPXML and Premiere XML timelines, reel-time SRT, the footage and a transparent overlay track ([ADR 0017](decisions/0017-export-to-editors.md)).
**API.** `uvicorn api.main:app` serves a job per upload. `POST /jobs` (multipart `video`, `style`,
`hook_strategy`) saves to `media/<job_id>/` and returns an id; a background thread runs
`hypercut.run.run_pipeline` (ingest, then transcribe and reframe together, then style, then analyze) and
writes `plan.json`. `GET /jobs/{id}` returns `status` (`queued|running|done|error`), the current `stage`,
`error`, `render` state, the plan and the file list. `PUT /jobs/{id}/plan` replaces the plan after
validation (e.g. a different `hook.chosen`, a fixed transcript). `POST /jobs/{id}/render` runs the render
project's `npm run render` into `output.mp4`; `GET /jobs/{id}/files/{name}` serves outputs. State is one
`job.json` per job, no database. `python -m hypercut.run VIDEO [--style ...] [--render]` runs the same
pipeline without the server. For re-editing (decision 0702): the first `PUT` keeps the pipeline's plan as
`plan.base.json` (returned as `base_plan`) and `POST /jobs/{id}/plan/restore` puts it back; `POST
/jobs/{id}/assets` imports a picture or a clip (clips are re-encoded to silent H.264, at most a minute and
1920 px on the longest side; 30 files per job) and `DELETE` removes one that is off the timeline; a plan whose `media` graphic
names a file the job does not have is rejected. `POST /jobs/{id}/assistant` runs the editor assistant on the
plan it is sent and returns the edited plan without saving it. CORS allows `HYPERCUT_WEB_ORIGINS` (default
`http://localhost:3000`). `python -m api.import_job FOLDER [--plan plan_split.json]` turns a CLI run's folder
into a web job. `POST /jobs/{id}/recut` re-cuts a plan for new pacing with the job's audio and returns it
unsaved (decision 0703). `POST /jobs/{id}/matte` makes the speaker cut-out once in the background (job
field `matte`); the editor calls it when green-screen effects get turned on, and renders make it if it is
missing. See ADRs [0701](decisions/0701-job-server-design.md) to
[0703](decisions/0703-recut-endpoint.md).


Later additions ([ADR 0704](decisions/0704-generation-recipes-variants-review-export-endpoints.md)): `POST /jobs/{id}/generate` fetches the pictures a plan waits for (or one again) and returns the plan unsaved; `GET/POST /recipes`, `DELETE /recipes/{name}` and a `recipe` field on `POST /jobs`; a `pictures` field on `POST /jobs` and `GET /generation` (what the engine can fetch, ADR 0020); `POST /jobs/{id}/variants` makes new jobs from other hooks and shorter cuts; `POST /jobs/{id}/review` has Claude check the last render; `POST /jobs/{id}/export` builds `hypercut-export.zip`. `PUT /jobs/{id}/plan` accepts the job's `gen-*` files as well as imports, and a render fetches pending pictures first.
**Web.** `web/` is a Next.js 14 App Router app (client components, no server code) that talks to the API at
`NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). `/` uploads a video with a style prompt (preset
chips fill the prompt) and a hook strategy; `/jobs/[id]` polls the job and shows the four stages, then the
editor (decision 0804), laid out like a video editor: a bin on the left (tabs for text and graphics, zoom and
layout tiles, the user's imported media with an import drop zone, removed blocks, the hook choice and the
transcript), the `@remotion/player` preview of the `HyperCut` composition imported from `render/src` (one
implementation of the look, no copy) in the middle, and an inspector plus the "Ask AI to edit" box on the
right. Below is a toolbar (undo, redo, split, duplicate, delete, timeline zoom, snap, restore original, save,
render, download) and a timeline in reel time with six tracks: Visuals, Overlays, Layout, Zooms, Video (the
kept segments, hook marked) and Captions (one block per caption line). Blocks drag to move, drag at the edges
to trim, snap to word starts and other edges, and anything in the bin drags onto the timeline (or is added at
the playhead on click). All edits are pure functions of the plan in `web/lib/timeline.ts`, built on the
renderer's own `buildTimeline`, with undo/redo in `web/lib/history.ts`; something inside a cold-open hook
shows twice and both copies move together. A Style tab in the bin sets speed, pauses (re-cut on the
server), cut style, end fade, the caption font and look, and the green-screen switch with its background; the
inspector can put any graphic behind the speaker, the bin adds effects around the speaker (orbit, fly out,
particles, decision 0610) and full-screen motion graphics (title and idea; the scene is designed at render,
decision 0612), and turning any of them on asks the API for the cut-out, which the preview uses once
it exists (decision 0805, 0901). Picking a hook or editing a word still goes through
`web/lib/rehook.ts`. Save and Render `PUT` the plan first. `npm test` in `web/` runs vitest (API client, hook
logic, timeline edits) and a production build. See
ADRs [0801](decisions/0801-nextjs-app-and-shared-composition.md) to [0805](decisions/0805-style-tab.md).


The editor also shows the graphics at the playhead as buttons under the preview, a colour for each text graphic, the prompt or search words behind every stock or generated picture with "Try another", and a Finish panel: check the render (0019), make variants and save the style as a recipe (0018), export for Final Cut, Resolve or Premiere (0017). The upload page lists saved recipes and has an optional, off-by-default "Use stock footage and AI pictures" box, disabled when no keys are set (0020). See [ADR 0806](decisions/0806-finish-panel-and-picture-controls.md).
## Claude calls

All of them go through `hypercut/llm.py`'s `ask_json`. By default it runs Claude Code headless
(`claude -p --output-format json`) on the user's own subscription; `HYPERCUT_LLM=api` switches to the
Anthropic API for when other people use the app. Every answer is parsed and validated with the pydantic
models before use. See [ADR 0003](decisions/0003-claude-via-subscription.md). The editor assistant
(`hypercut/assistant.py`, decision 0013) is the one call made after the pipeline: one per request, plus one per
batch of new illustrations. `ask_json(images=[...])` lets Claude look at pictures (stock thumbnails, review frames):
the CLI backend lets Claude Code read just those files, the API backend sends them as image blocks.

## Where things live

```
hypercut/        Python pipeline (one package per stage) + plan.py, llm.py
schema/          generated JSON schema + example plan
render/          Remotion project (TypeScript)
api/             FastAPI job server
web/             Next.js app
media/           uploads and outputs, git-ignored
docs/            this file, the decision records, hosting-plan.md
Dockerfile, docker-compose.yml, .env.example   one-command local run (ADR 0015)
```

Deployment: everything runs on the user's own computer, normally with `docker compose up` (the README has
the steps and every setting). Options for hosting it for other people are in [hosting-plan.md](hosting-plan.md).

## Cost

For personal use on a Claude subscription with local Whisper: nothing beyond the plan. With paid APIs,
about $0.05 to $0.15 of Claude and about $0.013 of Deepgram per 3-minute video. Stock footage is free; generated
pictures cost about $0.05 each and clips about $0.30 each through fal.ai, capped per video by
`HYPERCUT_GEN_BUDGET_USD` (default $2; ADR 0016).
