# 0004: Local faster-whisper by default, Deepgram optional

Status: accepted, 2026-10-17

**Decision.** Transcribe locally with faster-whisper (word timestamps on) by default. Offer Deepgram Nova-3
with `HYPERCUT_TRANSCRIBE=deepgram` and `DEEPGRAM_API_KEY`.

**Alternatives.** Deepgram or AssemblyAI only; WhisperX (adds forced alignment and diarization, heavier
install).

**Why.** Local is free and private, and uploads are local anyway. Deepgram is about $0.0043 per minute
(about $0.013 per 3-minute video) and much faster, so it is the upgrade path. WhisperX can replace
faster-whisper later if word timing needs to be tighter.

**Consequences.** First run downloads a Whisper model (the `small` model is about 500 MB). The transcript is
editable in the web app before rendering, because names and jargon will sometimes be wrong.
