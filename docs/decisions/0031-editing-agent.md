# 0031. The editing agent: several reels from one long recording

Status: accepted (2026-10-26)

## What

`hypercut/agent.py` turns one long recording (up to an hour) into up to 8 reels, in four steps that the person
can follow on the session page:

1. **Understand.** Normalize and transcribe the recording once (`ingest(..., max_seconds=LONG_SECONDS)`).
2. **Plan.** Claude reads the transcript as numbered sentences with times and proposes clips: one complete idea
   each, opening on a line that makes people stay, 20-75 s of source, whole sentences, no overlaps, with a
   title and why it works. Code checks every proposal and drops what fails. If Claude can't be asked or its
   answer leaves too few clips, code fills the rest: the densest sentence-aligned ~45 s window in each part of
   the recording. The plan is written to `agent.json` before any reel is made.
3. **Act.** Each clip is cut out frame-accurately (0.3 s of air either side) and made into a normal job by the
   usual pipeline, given its words from the transcript already made (`run_pipeline(..., transcript=)`), so
   Whisper runs once. One failed reel doesn't stop the others.
4. **Check.** The plan checks (ADR 0023) run on each reel and code fixes what it can, up to two rounds: a reel
   over 58 s ends on an earlier sentence, a hook that starts mid-sentence or runs long is swapped for another
   candidate that passes, a graphic that never shows, overlaps another or repeats is removed. Fixes are saved
   as a "review" version, so they are explained and undoable; what is left is listed on the reel.

`POST /agent` starts a session (a job folder with `kind: "agent"`), `GET /agent/{id}` reports its step and
clips; every reel is a job with `agent: <session>` and opens in the editor. The upload page's "It is a long
recording: make several reels from it" starts one; `python -m hypercut.agent` runs one from the command line.

## Alternatives

- **One pipeline run over the whole recording, then split the plan.** The analyze prompt, visuals and hooks are
  built for one short; per-clip runs reuse all of it unchanged and give each reel its own hook and graphics.
- **A free-form tool-using agent loop.** More flexible, but slow, costly on the subscription and hard to test.
  The fixed plan-act-check loop makes one Claude call to plan plus the usual calls per reel.
- **Transcribe each clip again.** Simpler, but minutes of Whisper per reel for words we already have.

## Consequences

- Clips are cut from the normalized recording, so each reel's job is self-contained (its own `normalized.mp4`)
  and portable like any other (ADR 0027).
- Claude sees only the transcript to plan; what is on screen (ADR 0024) is used inside each reel's run.
- A reel's own check can't fix everything (a clipped word, a reel that is too short); those are shown, not hidden.
