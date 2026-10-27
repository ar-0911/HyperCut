# 0104: A media manifest at ingest, and silent video accepted

Status: accepted, 2026-10-26 (changes ADR 0102 for files without sound)

**Decision.** Ingest writes `manifest.json` in the job folder: the original file (name, size, SHA-256, container,
duration, bit rate), the video stream (codec, stored and displayed size, rotation, orientation, average frame rate,
whether it is variable, pixel format, HDR), the audio (present, number of tracks, codec, channels, rate), the
normalized file, plain-language `warnings` and per-stage `stages` statuses (running, done, failed), which the
pipeline updates as it goes. `GET /jobs/{id}` returns its video, audio, warnings and stages; the job page lists the
warnings above the editor.

A file with no audio track is no longer rejected: ingest adds a silent track, so the reel is still made (reframed,
with any graphics added in the editor) and a warning says there are no captions or speech cuts.

Warnings: no sound; variable frame rate (converted to 30 fps CFR, ADR 0101); stored rotation (turned upright by
FFmpeg's autorotate); HDR (PQ or HLG, converted to standard range without tone mapping); smaller than 720 on the
short side (will look soft); more than one audio track (only the first is used).

**Alternatives.** Storing the facts in `plan.json` (`Source`): the plan is the edit, and the renderer has no use for
codec or rotation facts; like the visual index (ADR 0024), media facts stay beside it. Tone-mapping HDR with
`zscale`: not in every FFmpeg build; a warning is honest until it is needed. Keeping the rejection of silent video:
screen recordings and B-roll-only clips are real uses, and an empty transcript already gives a valid plan.

**Why.** Adi's product note asks for a proper ingestion pipeline with a media manifest and graceful handling of
missing audio, VFR and orientations. Writing down what ingest had to fix explains surprises ("why is it 30 fps?")
and is the base for later work: the SHA-256 recognizes a moved or renamed source for portable projects, and stage
statuses are what a resumable import needs.

**Consequences.** Hashing reads the whole upload once (about 1 s for 20 MB, a few seconds for 1 GB). Old jobs have no
manifest; everything treats it as optional. Multi-file import and duplicate-take detection (P2) will extend this file.
