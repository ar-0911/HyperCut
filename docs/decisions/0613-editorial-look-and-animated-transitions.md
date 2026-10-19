# 0613: Studio backgrounds, an editorial type look, and a few animated transitions

Status: accepted, 2026-10-19

**Context.** After the production test reel Adi asked for three things:
- Never a plain different-coloured background (the reel opened on the speaker over a flat gradient), because
  it does not look professional.
- Smoother, animated cuts ("the speaker just dropping off screen"), used sparingly and professionally.
- A look inspired by creators like Varun Mayya and 100xEngineers (font and style, as inspiration, not a copy).

**Decision.**
- **No flat backgrounds.** Claude can no longer pick a `gradient` background; analyze offers only the real
  background (original, blur, dim). Wherever a backdrop is drawn (split and full-screen visuals, behind
  cards and charts, a scene with no drawing, and a `color` or `gradient` background the user asks for), the
  renderer draws a studio set instead (`render/src/Backdrop.tsx`): a grid floor running to a horizon, a
  faint wall grid, soft light and a vignette, drifting slowly. A colour the user asks for tints its light.
  Old plans with `gradient` render as the set too, so the schema stays compatible.
- **Animated transitions, sparingly.** `plan.cuts` holds `{at, kind, length}`: at source time `at`, the last
  frame before it (footage, graphics and captions) is held and moved away over the incoming footage, which
  already plays: `drop` (it falls off the bottom under gravity, tipping), `whip` (a fast blurred pan),
  `zoom` (it pushes through toward the viewer) or `push` (the new shot slides up). They are picked by code,
  not Claude (`analyze/transitions.py`), after reframe: the cold open handing over to the story gets a
  drop; hard cuts between shots in the source (reframe now records them as `reframe.shots`) get the others,
  never the same kind twice in a row. At most three a minute, 12 s apart, never in the first or last 2 s,
  and a shot change only when it lands on the speaker alone (only the footage moves, so incoming graphics
  would sit still). Every other cut stays as `style.transitions` says. The AI edit box can add or remove one
  (`cut_transition`).
- **Type.** Two bundled fonts join the caption list: Instrument Serif (tall editorial serif, OFL) and Archivo
  Expanded (Archivo's width axis at 125%, OFL). Motion-graphic titles use Instrument Serif with words coming
  into focus one after another and the last word in the accent. Captions can sit in a rounded dark box
  (`caption.box`, a CSS colour) instead of an outline; `null` keeps the old outlined look.

**Alternatives.**
- **Transitions at every jump cut:** busy, the opposite of "sparingly"; jump cuts keep their short crossfade.
- **Claude choosing the transitions:** it never sees the picture, and shot changes come from reframe, after
  analyze; simple rules give consistent spacing for free.
- **Dropping only the cut-out speaker:** needs the matte, which is off by default; holding the whole frame
  works for every reel.
- **Copying a creator's exact look:** Adi said it should only inspire.

**Consequences.**
- A transition draws the footage twice for its few frames (held and live), so those frames render slower.
- Sources that are already vertical skip face detection, so they have no `shots` and only the cold-open
  transition.
- Two more font files (about 120 KB) in the render bundle.
