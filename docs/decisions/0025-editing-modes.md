# 0025. Editing modes are policies over the same engine

Status: accepted (2026-10-26)

## What

`plan.style.mode` (new, default `talking_head`) names how the reel is edited, next to the style, which names how
it looks. `hypercut/modes.py` defines four modes:

| mode | hook | pacing (keep / max silence) | camera | graphics | captions | cuts |
|---|---|---|---|---|---|---|
| talking_head | today's rules | preset | preset | preset | preset | preset |
| podcast | boldest standalone answer (with its question if needed) | 0.12 / 0.3 s | zooms often | balanced, big text and stats | karaoke, 3 words | editorial |
| product_demo | the problem solved or the best result | 0.15 / 0.5 s | few zooms, only to point | balanced, clean, labels and steps, footage kept clear | Inter, boxed, sentence case | hard |
| vlog | the most intriguing moment | 0.25 / 0.6 s (beats breathe) | few, longer, 1.1x | minimal, cinematic, scenes over text | preset | smooth, 1.2 s fade out |

A mode is two things: a patch of `Style` settings (pacing, camera, graphics, captions, transitions) and a paragraph
of planner guidance appended to the analyze prompt (what makes a hook, what to keep, what graphics suit it).

Order of precedence: preset, then mode, then whatever the style prompt, recipe or editor set beyond the preset
(`modes.asked_for`). So "product demo, but in Bebas Neue" keeps Bebas Neue.

Picked on the upload page ("What are you making?"), `mode` on `POST /jobs`, `--mode` on the CLI, or later with
the assistant ("edit this like a podcast clip", the `mode` op). `GET /modes` lists them.

## Alternatives

- **More style presets.** Presets already exist (six looks), but a look and an editing policy are independent: a
  product demo can be bold or minimal. Mixing them would multiply presets.
- **Separate pipelines per mode.** Every mode would need its own checks, editor and renderer support. One engine
  with policies keeps every feature (history, checks, QA, the editor) working for every mode.
- **Let Claude infer the mode from the transcript.** Possible later as a default suggestion, but the user knows
  what they are making, and an explicit choice is cheaper and predictable.

## Why

Adi's product note asks for modes as policies on one engine, switchable later without losing the edit. A patch plus
guidance is the smallest thing that changes the editing decisions (hooks, pacing, shot choice, graphic density,
caption style) while everything downstream stays the same.

## Consequences

- Switching mode re-applies from the preset, so nothing of the old mode is left behind, and re-cuts pauses when the
  pacing changed. The hook, graphics and manual edits stay; the guidance applies to the next full analysis.
- `style.mode` is additive and optional in the schema; old plans read as talking head; the renderer ignores it.
- Diffs and version history say "Editing mode: Talking head → Podcast clip".
- Speaker-following for multi-person podcasts is separate work (speakers, P1).
