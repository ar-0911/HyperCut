# 0616. Every export is loudness-normalized to -14 LUFS

Status: accepted (2026-10-26)

## What

After Remotion renders `output.mp4`, `hypercut/audio.py` levels its sound in place with FFmpeg's two-pass
`loudnorm`: measure, then one linear gain to -14 LUFS integrated with true peak under -1.5 dBTP (a limiter only
where needed). The picture is stream-copied, so this takes seconds. `HYPERCUT_LOUDNESS` sets another target or
`off`. The overlays-only export (ADR 0017) has no sound and is skipped. If it fails, the render keeps its own levels
and the export check (ADR 0023) says so.

## Alternatives

- **Normalize the source at ingest.** Cuts, J-cuts and fades change the level of the finished reel; levelling
  the result is what the viewer hears.
- **One-pass `loudnorm`.** Dynamic gain that pumps on speech with pauses; the two-pass linear mode doesn't.
- **Leave it to the platforms.** They turn loud uploads down but don't turn quiet ones up, and clipping in the
  file stays clipped.

## Consequences

- The v2 test reel went from -16.5 LUFS with peaks at +0.1 dBTP (clipping) to -14.2 LUFS, -1.1 dBTP; every export
  check passes.
- A render takes ~10-20 s longer per minute of reel.
