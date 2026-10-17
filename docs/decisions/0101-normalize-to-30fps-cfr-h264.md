# 0101: Normalize to 30 fps constant frame rate H.264/AAC, 16 kHz mono wav

Status: accepted, 2026-10-17

**Decision.** Ingest re-encodes every input to `normalized.mp4`: constant 30 fps (`fps=30`, `-fps_mode cfr`),
H.264 (`libx264`, CRF 18, `veryfast`, yuv420p), AAC 192k, `+faststart`. Audio for transcription goes to
`audio.wav`: 16 kHz, mono, 16-bit PCM. `Source` is read back from the normalized file, not the original.

**Alternatives.** Keep the original and only remux (fast, but variable frame rate phone footage breaks
frame-accurate cuts and Remotion's frame sampling). Match the source frame rate (output is fixed at 30 fps by
ADR 0002, so this would only defer a conversion). Lossless intermediate (huge files for no visible gain).

**Why.** One known timebase for every later stage: reframe samples frames, the renderer maps source seconds to
frames, and Whisper wants 16 kHz mono. CRF 18 keeps the speaker's pixels visually untouched through the second
encode. Probing the output means `Source` reports what the renderer will actually see, including autorotated
phone video.

**Consequences.** Ingest costs one encode (roughly real time or faster at `veryfast`). Sources above 30 fps are
decimated. The original is never modified.
