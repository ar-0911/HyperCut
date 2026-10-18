# 0610: Effects around the speaker

Status: accepted, 2026-10-18

**Decision.** Three graphic types happen around the cut-out speaker, passing both behind and in front of them:

- `orbit` (`props.items`: 2-5 emoji or 1-2 word labels): a ring circling the speaker's shoulders, an ellipse
  centred just below the face (0.38 of the width across, 0.05 of the height deep), turning at 1.1 rad/s.
- `fly_out` (`props.items`): items bursting from behind the head toward the camera one after another, each for
  1.4 s, growing as they come.
- `particles` (`props.kind`: sparkles, bokeh, confetti, embers): 34 seeded particles drifting through the frame
  at random depths; confetti falls, the rest rise.

Each effect is a pure function of time (`render/src/Around.tsx`) that gives every element a position, size and
depth (0 far .. 1 near). The frame is drawn in two passes: elements with depth below 0.5 go between the
footage and the cut-out (the speaker hides them), the rest go over the cut-out with the other overlays. Front
elements fade out within 60 px of a box around the tracked face (0.34 of the width wide, 0.24 of the height
tall), so nothing ever covers the face; the face itself is never in either pass's way, because behind
elements are hidden by the speaker. Without a cut-out every element is drawn in front, with the same face
clearance. They are drawn only in speaker stretches and only when `style.depth.enabled`; they never open the
split panel.

Analyze asks for them in the same call as behind titles (`around`, about three a minute, only with
`style.depth.around`, which defaults to true once depth is on), drops overlapping ones and those outside
speaker stretches, and caps orbit at 6 s, fly-out at 3.5 s and particles at 12 s. The AI edit box has an
`around` op, the editor has Orbit, Fly out and Particles tiles, and adding any of them turns the green-screen
effects on. The style prompt's opt-in keyword check (ADR 0901) also accepts "around me", "immersive",
"orbit", "particles", "sparkles", "confetti" and "in front of me".

**Alternatives.** Real 3D (three.js, depth from a model) for occlusion: heavier, and the cut-out already gives
the one depth boundary that matters, the speaker's silhouette. Splitting each element into its own behind or
front graphic in the plan: the plan would carry animation detail, and editing one effect would mean editing
many entries. Drawing front effects anywhere and trusting the model to keep them off the face: the face rule
is a hard rule, so it is enforced in the renderer.

**Consequences.** One plan entry per effect, editable as a block on the timeline. Emoji need a colour emoji
font in the rendering Chromium (Noto Color Emoji). An element passing the face on the near side disappears
briefly instead of crossing it, which reads as it passing just beside the head. Effects in split or visual
stretches are dropped by analyze and not drawn by the renderer.
