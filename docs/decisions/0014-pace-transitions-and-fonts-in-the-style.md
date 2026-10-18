# 0014: Pace, cut transitions and caption fonts live in the style

Status: accepted, 2026-10-18

**Decision.** Three additive fields in `Style`, all with defaults so old plans still validate:
- `pacing.speed` (0.5 to 2, default 1): playback rate of the whole reel. Plan times stay in source
  seconds; only the source-to-reel mapping divides by it.
- `pacing.keep_pause` (0 to 1 s, default 0.15): silence kept on each side of a removed pause.
- `transitions {style: hard|smooth|zoom, length, fade_in, fade_out}` (default `smooth`, 0.2 s, no fade in,
  0.8 s fade out at the end).

`CaptionStyle.font` stays a free string, but its description lists ten bundled Google fonts
(`CAPTION_FONTS`) and the renderer loads exactly those.

**Alternatives.** Retime the plan itself for slow motion (every stored time would change, and undo,
the assistant and the timeline would all need to know). Per-cut transitions (more control, but a
reel reads as one style and the editor would need a new track). Any web font by name (needs network at
render time and fails silently).

**Why.** Adi found the reels too fast and the cuts too abrupt, and wanted font choice. A single global
speed and transition style give a professional, consistent look from one control each, and keeping
times in source seconds means no other stage changes.

**Consequences.** Every source-to-reel mapping (Python `edit.py`, `timing.ts`, the web timeline) is
speed-aware. Old plans get `smooth` transitions and a 0.8 s fade out when re-rendered, which changes their
look slightly; set `transitions.style` to `hard` and `fade_out` to 0 for the old look.
