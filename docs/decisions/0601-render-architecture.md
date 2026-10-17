# 0601: Render architecture: one composition, pure logic modules, per-segment video

Status: accepted, 2026-10-17

**Decision.** `render/` is a Remotion 4 project with one composition, `HyperCut`, whose props are
`{plan, videoSrc}`. Size, fps and length come from the plan through `calculateMetadata`. The video layer is
one `<Sequence>` + `<OffthreadVideo startFrom>` per entry of `plan.segments`; captions and graphics are a
single overlay layer driven by the *source time* of the current output frame. All decisions that can be
computed without React live in pure modules with vitest tests: `timing.ts` (source <-> output mapping),
`layout.ts` (reframe interpolation, crop rectangle, zoom curve, graphic placement), `captions.ts`
(line grouping, per-word animation state).

**Alternatives.** (a) A single `<OffthreadVideo>` with `playbackRate`/seek tricks for cuts. (b) Pre-cutting
the video with FFmpeg and rendering overlays on the result. (c) Keying overlays to *output* time computed
by the analyzer.

**Why.** (a) cannot jump over cuts reliably. (b) adds a lossy re-encode of the speaker and a second
pipeline step. (c) would make analyzers know about cuts, which ADR 0001 rules out. Driving overlays from
source time makes the cold open free: the hook span is played twice, and a caption or graphic whose span
covers it shows both times with no special case. Frame lengths are `round(duration * fps)` per segment
(minimum 1) and summed, so rounding never drifts and output length is exact.

**Consequences.** A graphic that crosses a cut is clipped at the cut and continues after it (its animation
clock is source time). A caption line is grouped from the words that survive the cuts (word midpoint kept),
so lines never straddle removed material. `OffthreadVideo` needs the video served over HTTP; the render
script handles that (ADR 0604).
