# 0002: Up to 3 minutes in, 15 to 60 seconds out, 1080x1920

Status: accepted, 2026-10-17

**Decision.** Accept 10 seconds to 3 minutes of input. Produce a 9:16, 1080x1920, 30 fps short, usually
15 to 60 seconds after cuts.

**Alternatives.** 2 minutes (the first suggestion), or long-form input of 20+ minutes.

**Why.** 3 minutes covers almost all raw takes for a short, keeps the whole transcript in one Claude call,
and keeps transcription and rendering to a few minutes. Long-form clipping needs chunked analysis and
multi-clip output, which is a different product shape.

**Consequences.** Ingest rejects longer files with a clear message. Raising the cap later mostly means
chunking the analyze stage.
