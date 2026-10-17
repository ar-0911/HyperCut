# 0203: Transcribe decodes the wav itself before handing it to faster-whisper

Status: accepted, 2026-10-17

**Decision.** For ingest's 16 kHz mono 16-bit wav, the Whisper backend reads the samples with the standard
`wave` module and passes faster-whisper a float32 array. Any other file is still passed by path.

**Alternatives.** Pin `av<14` in the `whisper` extra; wait for a faster-whisper release that fixes it.

**Why.** faster-whisper 1.2.1 calls `av.open(..., metadata_errors=...)`, an argument PyAV 14+ removed, so a
fresh install crashes before transcribing (found on the first real-footage run). Ingest already produces
exactly the format Whisper wants, so decoding it is a few lines with no dependency and works on any PyAV.
Pinning PyAV would fight other packages and break again with the next release.

**Consequences.** Whisper never touches PyAV on the normal path. A wav in another format falls back to
faster-whisper's own decoder and so still needs a compatible PyAV.
