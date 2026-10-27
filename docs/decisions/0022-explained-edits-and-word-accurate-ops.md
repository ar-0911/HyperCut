# 0022. Every edit explains itself; AI edits are proposals; word-accurate cuts

Status: accepted (2026-10-26)

## What

- `hypercut/diff.py` explains the difference between any two plans in creator words: "Removed 2.4 s at
  0:12.3", "Added an illustration “Rocket launch” at 0:10.0-0:13.0", "Caption “Kachaba” now reads “Ka'Chava”",
  "Caption font: Montserrat → Inter", "Reel is now 48.2 s (-2.4 s)". Times are reel times. It is used for every
  version (ADR 0021), every assistant answer (`explanation` next to the old `changes`) and recovered drafts.
- `hypercut/explain.py` explains the first cut from the plan itself, no Claude call: the hook and Claude's
  reason for it, pauses and filler words removed, speech left out (with the words quoted), where the reel
  ends, and each graphic with the words it sits on. `GET /jobs/{id}/explain`; the editor's "Why this cut" panel
  lists it and seeks the player on click. Pauses under 0.5 s are only counted in the summary.
- The assistant's answer is a proposal: the preview shows it, with its explanation, until the user picks
  "Keep it" (saved as an `assistant` version with the request as its note) or "Reject"; "Show before / after"
  switches the preview between the two.
- New assistant operations work on word timings, so a request lands exactly:
  `remove_pause` (`at`, `side`: the pause before what starts there, after what ends there, or the nearest),
  `tighten` (every pause in a stretch) and `cut_words` (exactly the spoken words in a stretch, cut between
  words so none is clipped). The caption summary Claude sees now marks `[pause 1.2s]` and uses each word's start.
  The cuts keep the style's `keep_pause` on each side. Pure functions in `hypercut.edit`
  (`reel_words`, `pauses`, `pause_near`, `pause_cut`, `word_cut`).

## Alternatives

- **Have Claude write the explanations.** A second call per request, can disagree with what was applied, and
  nothing for manual edits. Computing them from the plans is always true and free.
- **Per-operation accept/reject.** Ops interact (a cut moves later reel times; new illustrations are drawn per
  batch), so rejecting one means re-running the rest. Whole-proposal accept/reject with before/after first;
  per-op can come with the typed op layer.
- **Store a reason on every plan item.** A schema change in every stage for something derivable today; can be
  added later where it can't be derived (e.g. why this shot, once the visual index exists).

## Consequences

- "Remove the pause before the second answer" needs Claude only to find where the second answer starts; the
  cut itself is computed.
- Explanations are only as specific as the plan: they say what and where, and why only where the plan records it
  (hook reasons, the words under a graphic).
