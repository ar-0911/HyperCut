# 0610: Effects around the speaker

Status: accepted, 2026-10-18

**Decision.** Three graphic types happen around the cut-out speaker, passing both behind and in front of them:

- `orbit` (`props.items`: 3-4 objects in 1-3 words, e.g. "stack of coins"): drawn graphics circling the
  speaker's shoulders, an ellipse centred just below the face (0.38 of the width across, 0.05 of the height
  deep), turning at 0.8 rad/s, each item popping in a beat after the previous one.
- `fly_out` (`props.items`): drawn graphics bursting from behind the head toward the camera one after
  another, each for 1.5 s, growing as they come.
- `particles` (`props.kind`: sparkles, bokeh, confetti, embers): 12-24 seeded particles drifting through the
  frame at random depths, kept faint so they read as atmosphere; confetti falls, the rest rise.

Items are graphics, not emoji or words (Adi, 2026-10-18). Each item is drawn by Claude as a small sticker SVG
(`hypercut.analyze.visuals.draw_icons`: flat vector, thick dark outline, the style's accent, no gradients or
`<defs>` so several can share the frame without id clashes, sanitized like the illustrations) and stored in
`props.art` keyed by the item's text. Analyze and the AI box draw new items at once; items added or renamed in
the editor are drawn before the next render (`run.draw_new_around`), and the preview shows a built-in icon
until then. The renderer draws each with a white die-cut edge and a soft shadow, far ones a little darker and
softer. Without a drawing (failed, or not drawn yet) it uses one of 20 built-in icons picked by the item's
words (`render/src/icons.ts`), never the raw text.

They are used sparingly, like an editor would: analyze asks for them only on the one or two moments that call
for one (a reveal, a big claim, the speaker naming concrete things), at most one a minute.

Each effect is a pure function of time (`render/src/Around.tsx`) that gives every element a position, size and
depth (0 far .. 1 near). The frame is drawn in two passes: elements with depth below 0.5 go between the
footage and the cut-out (the speaker hides them), the rest go over the cut-out with the other overlays. Front
elements fade out within 60 px of a box around the tracked face (0.34 of the width wide, 0.24 of the height
tall), so nothing ever covers the face; the face itself is never in either pass's way, because behind
elements are hidden by the speaker. Without a cut-out every element is drawn in front, with the same face
clearance. They are drawn only in speaker stretches and only when `style.depth.enabled`; they never open the
split panel.

Analyze asks for them in the same call as behind titles (`around`, at most one a minute, only with
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

**Consequences.** One plan entry per effect, editable as a block on the timeline. Drawing costs one extra Claude
call per six items, only when there are effects around the speaker. An element passing the face on the near side disappears
briefly instead of crossing it, which reads as it passing just beside the head. Effects in split or visual
stretches are dropped by analyze and not drawn by the renderer.
