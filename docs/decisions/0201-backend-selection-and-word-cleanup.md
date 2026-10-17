# 0201: Backend selection, lazy imports and word cleanup

Status: accepted, 2026-10-17

**Decision.** `transcribe(wav_path, backend=None) -> Transcript`. The backend is the argument, else
`HYPERCUT_TRANSCRIBE` (`whisper` or `deepgram`), else `whisper`. faster-whisper reads its model from
`HYPERCUT_WHISPER_MODEL` (default `small`) and runs with `word_timestamps=True` and `vad_filter=True`.
Deepgram uses Nova-3 through the prerecorded REST endpoint with `httpx` (`smart_format`, `punctuate`,
`detect_language`), authenticated by `DEEPGRAM_API_KEY`. Both libraries are imported inside the functions
that need them. Every backend's output passes through one `_clean` step that drops blank words and makes
timings valid for the plan (sorted, non-overlapping, `end > start` by at least 20 ms).

**Alternatives.** The Deepgram SDK instead of `httpx` (one more dependency for one POST); a backend registry
or plugin system (two backends do not need one); trusting backend timings as they are (Whisper does emit
zero-length and overlapping words, which `Word`/`Span` validation rejects, and that would fail the whole job).

**Why.** Failures stay clear and local: a missing extra or API key raises `TranscribeError` with the install
or config hint, and the test suite imports neither library. VAD filtering stops Whisper inventing words in
silence, which matters because the analyze stage cuts on word gaps. Repairing timings in one place means
downstream stages can rely on the `Transcript` invariants.

**Consequences.** Tests fake the seams `_load_whisper_model` and `_deepgram_request`; no network or models.
Deepgram speaker ids are stored as strings, and diarization is not requested yet. Language is detected
(Deepgram) or reported (Whisper) rather than forced; add an override if mis-detection shows up.
