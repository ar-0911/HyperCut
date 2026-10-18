# 0609: Green-screen layers in the renderer

Status: accepted, 2026-10-18

**Decision.** The composition takes an optional `matteSrc` (the speaker cut-out, ADR 0901). With it and
`style.depth.enabled`, each frame is drawn in four layers:
1. The footage, as today, with its background kept, blurred (22 px), dimmed (38% brightness), or covered by a
   replacement inside the speaker panel: a colour (radial, from `color` or the accent), the drifting accent
   gradient used behind illustrations, or an imported picture or clip. `parallax` makes a replacement drift
   and breathe slowly. This layer still carries the sound.
2. Graphics with `layer: "behind"`, only where the speaker fills the frame: `kinetic_text` becomes a big
   Anton title centred just above the face (the head covers the bottom of the letters), anything else fills
   the frame behind the speaker.
3. The cut-out speaker, with the same crop, zoom and crossfade as the footage, and a soft drop shadow over
   a replaced background. This pass is only mounted on frames where something is behind the speaker or the
   background is not the original, so other frames cost nothing extra.
4. The usual overlays and captions.

Behind graphics never open the split panel. Without a cut-out (not made yet, failed, or a split/visual
stretch) they are placed in front like any other graphic, which keeps them off the face. The render script
picks up `matte.webm` next to the video (or `--matte`), and background media from the asset folder.

**Alternatives.** Compositing in Python with FFmpeg before Remotion (a second full encode, and the browser
preview would not match). One video element with a canvas mask per frame (slow, and not how `OffthreadVideo`
renders).

**Why.** The speaker's pixels are the original pixels, only layered; graphics behind the speaker can't
cover the face by construction. The same composition runs in the editor preview, where Chrome plays VP9
alpha natively.

**Consequences.** Frames that use the effects decode two videos, the second as PNG (transparent), so those
stretches render more slowly. A replaced background is drawn per panel, so in split mode only the speaker's
half changes.
