# 0202: SRT lines are grouped by words, characters, pauses and sentence ends

Status: accepted, 2026-10-17

**Decision.** `to_srt(transcript)` starts a new subtitle line after sentence-ending punctuation (`. ? !`),
after a pause over 0.8 s, or when a line would exceed 6 words or 42 characters. A line spans from its first
word's start to its last word's end. Times are on the source timeline.

**Alternatives.** Fixed N words per line (splits sentences badly); grouping by Whisper segments (not available
from Deepgram, and segments are often too long); splitting at commas as well (more lines, little gain).

**Why.** The limits match common subtitle practice (about 42 characters per line) and work from word timings
alone, so both backends produce the same kind of SRT. The animated captions in the video use
`CaptionStyle.words_per_line` instead; the SRT is only the plain export.

**Consequences.** The SRT reflects the source timeline, not cuts or the moved hook. If a post-edit SRT is
wanted, the renderer or API must remap word times through `segments` first.
