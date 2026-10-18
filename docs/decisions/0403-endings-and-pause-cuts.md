# 0403: The reel ends on a finished sentence, and small pauses are not cut

Status: accepted, 2026-10-18

**Decision.** The analyze call also returns `"ending": {"word": i, "why"}`, the last word worth keeping.
Code (`ending_word`) accepts it only if it is in the second half of the transcript and ends a sentence;
otherwise it takes the last sentence-ending word in the second half (or the last word). `end_at` cuts the
segments 0.4 s after that word, and the renderer fades out over `transitions.fade_out`.

Pause cuts keep `pacing.keep_pause` (0.15 s, up from 0.08) on each side, and a pause is only cut when at
least 0.25 s (`MIN_CUT`) would go. `recut(plan, wav)` rebuilds the segments for new pacing, keeping the
hook, the strategy and the chosen ending.

**Alternatives.** Always end at the last word (what v2 did: it ended on the fragment "And I'd like to
go." and a slate card). Let Claude pick the end with no check (one bad index ends the reel mid-word).
Cut every pause over `max_silence` however little it saves (v2: many 0.05 to 0.1 s jumps).

**Why.** An abrupt ending and choppy micro-jumps were the two things that made v2 feel unprofessional.
A jump cut that removes a tenth of a second saves nothing and shows a visible jump.

**Consequences.** Reels run slightly longer. Old plans keep their segments until re-cut (the editor's
"Pauses" control or the assistant's `pacing` op).
