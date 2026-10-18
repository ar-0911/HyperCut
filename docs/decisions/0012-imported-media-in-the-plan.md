# 0012: Imported footage and pictures are a `media` graphic in the edit plan

Status: accepted, 2026-10-18

**Decision.**
- A new graphic type, `media`, holds a picture or clip the user imported in the editor. Props: `src` (a file
  name in the job folder, never a path), `kind` (`image` or `video`), `fit` (`cover` or `contain`),
  `trim_start` (seconds into the clip), `duration` (clip length) and `label`.
- It is a visual graphic like `illustration`: it fills the split panel, or the whole frame in a `visual`
  span, and a `speaker` span opens the split panel for it. So the speaker's face is never covered unless the
  user picks full screen.
- Imported clips are always muted; the speaker keeps the audio.
- The analyze stage never proposes `media` (`GENERATED_GRAPHIC_TYPES` excludes it), because only the user's
  uploads can fill it.

**Alternatives.** A separate `broll` list in the plan (cleaner name, but every consumer that already handles
visual graphics, from layout fallbacks to the timeline, would need a second code path). Replacing the
speaker video in `segments` with the clip (a true cut-away, but breaks "the speaker's pixels are a single
source" and the face-tracked crop). Keeping clip audio (needs a mix and volume UI; deferred).

**Consequences.** Additive and backward compatible: old plans have no `media` graphics. The sample plan
carries one, so the schema test exercises it. A plan with `media` needs its files next to the video at render
time (ADR 0607) and the API checks they exist (ADR 0702).
