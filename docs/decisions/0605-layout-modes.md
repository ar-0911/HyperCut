# 0605: Layout modes (speaker, split, visual) and the illustration graphic

Status: accepted, 2026-10-17

**Decision.**
- *Modes.* `EditPlan.layout` lists spans of source time with a `mode`. Outside every span, and for
  an empty list, the mode is `speaker` (speaker full frame, graphics in bands as before). `split` puts
  the speaker in the bottom half (`SPLIT = 0.5`, a 1080x960 panel, cropped with `cropRect` for that panel
  size) and the visual graphics in the top half over an animated backdrop. `visual` covers the whole
  frame with the visual graphic while the speaker keeps playing (and is heard) underneath, like B-roll.
- *Visual graphics.* `illustration`, `kinetic_text`, `stat_card` and `list_build` carry a panel. Other
  graphics stay "placed": in split a lower third sits at the foot of the speaker panel (0.88H), an emoji
  burst centers in the top panel and the progress bar hugs the top edge; over a full-frame visual they sit
  at the art's foot (0.74H) and emoji bursts are drawn at 60% size.
- *Never an empty panel.* A split/visual span with no visual graphic on screen renders as `speaker`
  (`modeAt`). The entrance clock counts from the start of the span or of the run of touching visuals,
  whichever is later, and back-to-back spans of one mode count as one, so nothing re-animates at a seam.
- *Animation.* Entering split, the speaker panel's top eases from 0 to 0.5H over 0.3 s (ease-in-out
  cubic), revealing the top panel behind it, and the caption line travels from the style position to the
  seam with it. A visual fades and scales (1.06 to 1) in over 0.25 s. Leaving is a cut. The backdrop is a
  dark gradient with two accent-colored radial glows whose positions are sines of the frame number.
- *Captions.* Speaker: `style.caption.position`. Split: centered on the seam (0.5H), where they cover
  neither the art nor the face. Visual: bottom (0.82H).
- *Illustration.* `props.layers` are complete SVG element strings, sanitized server-side, injected with
  `dangerouslySetInnerHTML` into `<g>`s under one `<svg viewBox>` (default `0 0 1000 800`) with optional
  `defs`. Layers pop in in order (stagger `min(0.2 s, 50% of span / layers)`, ease-out-back scale
  0.85 to 1, rise 40 units, fade), the art drifts 1 to 1.05 over its span and fades out in the last 0.2 s.
  An optional `title` sits above in the theme font. Art is fitted to its box: the top panel (0.03H to 0.44H)
  in split, 0.06H to 0.74H in visual, a 0.7W x 0.26H card in the band `placeGraphic` picks in speaker mode.
- *Determinism.* No CSS animations, no `Math.random`: every frame is a function of the frame number.

**Alternatives.** Picture-in-picture speaker over full-frame art (covers the art, small face); a variable
split ratio per span (more for Claude to get wrong, little gain); generating raster images (slow, needs a
model and network, can't be edited in the plan); falling back to an empty branded panel when no visual is
active (looks broken); CSS keyframe animations (not frame-accurate in Remotion renders).

**Why.** The user asked for "speaker below, animations above" and a mix of speaker-only, split and
visual-only. Keeping the mode on its own timeline in the plan lets analyze choose the rhythm while the
renderer guarantees the geometry. SVG layers are tiny, editable, resolution-free and safe to animate per
layer.

**Consequences.** Split halves the speaker's size; a wide source shows more background in the panel. A
span with no visual simply plays as speaker, so analyze must pair each split/visual span with a visual
graphic. SVG ids in `defs` are global to the page: two illustrations on screen at once with the same id
share it. Text graphics are scaled 1.15x over a full-frame visual; long lists are shrunk to fit their box.
