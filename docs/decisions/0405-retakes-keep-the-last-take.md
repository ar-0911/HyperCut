# 0405. Retakes: keep the last take

Status: accepted (2026-10-26)

## What

`hypercut/analyze/takes.py` finds retakes in the transcript, from word timings only, and the cut stage removes
the earlier takes along with any short stumble between them:

- the same sentence said again (word similarity of at least 0.8, both at least 4 words), starting within 8 s of
  the first one's end, with at most a 3-word aside between them ("Sorry.");
- a sentence that breaks off and starts over: a fragment of 3 or more words that the next sentence begins with,
  or the opening words said twice inside one sentence ("so the reason so the reason this works").

The last take is kept, since people repeat a line to get it right. `style.pacing.remove_retakes` (default on)
turns it off; the first cut's explanation lists each one as "Cut an earlier take of ...".

## Alternatives

- **Ask Claude which take is best.** Better on content, but a call per recording and no better on timing; the
  rule is right for the common case and free.
- **Keep the first take.** People usually redo a line because the first was wrong.
- **Fuzzy matching across the whole recording.** Catches more, but a point made again later on purpose is not a
  retake; the 8 s window and the 3-word aside limit keep it to real retakes.

## Consequences

- No false positives on the test montage (198 words); retakes are tested on synthetic transcripts. Whisper
  sometimes drops a repeated phrase from the transcript, and then there is nothing to cut.
- If the planner's hook falls in an earlier take, that part of the hook is cut with it; plan checks flag a hook
  that starts mid-sentence.
