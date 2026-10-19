# 0612: Full-screen motion graphics, designed per moment as 3D scenes

Status: accepted, 2026-10-19

**Context.** Adi wanted a few places where the reel is only motion graphics for 2-3 seconds, and the
illustrations there should look real and move the way the thing moves (DNA should turn as a double helix,
not sit as a flat drawing). He also asked that the graphics come from what is said in each video, not from a
fixed set (DNA, a globe and a network every time).

**Decision.**
- A new graphic type, `motion` (`props: {title, idea, scene}`), fills the whole frame while the speaker keeps
  talking. The renderer gives it the full frame whatever the layout span says (`modeAt`), and analyze also
  marks its span `visual` and clears other visuals, stage graphics and effects around the speaker there.
- **Picking.** The main analyze call returns `"motion"`: at most two a minute (usually one or two, none if
  nothing fits), 1.8-3.2 s, never in the first 2 s, each with a 1-4 word title and the idea of the one thing to
  show. Only concrete things, places, processes or numbers.
- **Designing.** One more Claude call (`motion.design_scenes`) designs every scene from the words around it.
  Claude writes a small JSON scene language rather than code: objects with a shape, a colour, a finish and
  how they move. Shapes are primitives (sphere, rounded box, cylinder, cone, torus, capsule), turned profiles
  (`lathe`: bottles, cans, cups), extruded SVG outlines, 3D text, tubes along points (a pour, a heartbeat
  line) and a few patterns that are hard to build by hand (a DNA double helix, a dotted globe, a network,
  growing bars, and stacks, rings and grids of any object). Finishes: glossy, metal, matte, glass, emissive.
  Moves: spin, float, pulse, enter (sprung, from a side or scaling up), grow, draw on, orbit, fall.
  `clean_scene` keeps only known fields, clamps every number and bounds the nesting and object count, so a
  bad answer can only produce a smaller scene.
- **Drawing.** `render/src/Motion.tsx` draws the scene with three.js through `@remotion/three`, with
  three's built-in room environment for reflections and soft light (no download). Every pose is a pure
  function of time, so renders repeat exactly. Entrances use a damped spring with a small overshoot.
- **Framing.** The renderer measures the scene at rest (`boundsOf`: each object's box at its landing place,
  turned and scaled, padded for floats and orbits) and scales and centres it into the space under the title
  and above the captions (`fitScene`), so Claude can build at real proportions without placing it on screen.
- **Look.** The scene stands in a studio with a grid floor and a soft contact shadow, `light` (pale grey) or
  `dark` (near black), chosen by Claude per scene; the title is set in Instrument Serif over it (ADR 0613).
- **Editing.** The editor's bin adds a motion graphic; the inspector edits its title and idea, and clearing
  the scene there makes the render design it again (`run.draw_new_around`). The AI edit box has a `motion`
  operation.

**Alternatives.**
- **A fixed library of 3D templates** (DNA, globe, network, charts): rendered well, but Adi rejected it: every
  video would get the same few pictures.
- **Claude writing three.js or React code:** the most freedom, but untrusted code in the renderer and far
  more ways to fail; the scene language is validated data.
- **Generated video or images (diffusion):** costs per call, slow, and does not move the way the subject
  does; the project runs on the user's subscription.
- **Lottie or SVG animation:** flat; Adi asked for realistic, moving illustrations.

**Consequences.**
- One more Claude call per pipeline run (about a minute for three scenes), only when analyze picked moments.
- The render needs WebGL: Chromium runs it in software (`gl: 'swiftshader'`), so motion frames are slower to
  render than footage. The web preview uses the browser's WebGL.
- New dependencies in `render/` and `web/`: three 0.169, @react-three/fiber 8.17 and @remotion/three 4.0.250
  (all MIT).
- Scenes are as good as Claude's design; the validator keeps them safe, not beautiful. The prompt sets the bar
  (one hero subject, one satisfying change, a held end, no emoji or clip art).
