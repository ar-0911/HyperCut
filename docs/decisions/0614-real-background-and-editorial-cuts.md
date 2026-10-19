# 0614: The real background by default, and editorial cuts

Status: accepted, 2026-10-19

**Context.** After the motion-graphics test reel (0612, 0613) Adi asked for two things:
- Don't change the background. The speaker cut-out is not clean enough, so effects should animate over the
  real background. Keep the cut-out code, but use it only when a different background is specifically asked
  for. Even with the real background, there should be animated overlays wherever there is space.
- The cuts are not smooth. Look at how editors join talking-head footage (A-roll, B-roll, J-cuts and so on)
  and implement that.

Editors hide or soften jump cuts in a few standard ways:
- J-cuts and L-cuts: the sound and picture of a cut change at slightly different moments.
- B-roll cutaways laid over the cut.
- A punch-in (reframing tighter) on alternate pieces, so a jump cut reads as a camera change.
- Cutting on motion.

Jump cuts themselves are an accepted short-form style ([Vimeo](https://vimeo.com/blog/post/j-cuts-l-cuts),
[PremiumBeat](https://www.premiumbeat.com/blog/5-ways-to-hide-jump-cuts),
[No Film School](https://nofilmschool.com/easy-ways-to-hide-jump-cuts-your-next-video)).

**Decision.**

**The speaker is cut out only when asked.**
- New `style.depth.cutout` (default false). Only with it does the render use `matte.webm`, and only with it does
  the pipeline make one (`needs_matte`).
- It is set by explicit asks only:
  - a style prompt that names a background, backdrop, green screen, cut-out or something behind the speaker
    (a keyword check overrules Claude, as for `depth.enabled`);
  - the AI box `background`, `behind_text` and `layer: behind` ops, a `scene` stage graphic, and "Cut the
    speaker out" in the Style tab.
- Without it, analyze asks for no titles behind the speaker, no `backgrounds` stretches and no scenes, and the
  prompt says the real background stays as filmed.
- Plans from before the field keep a background they had changed: a `depth.background` other than original,
  or any changed `backgrounds` stretch, implies `cutout` (in `plan.py` and in `normalizePlan`).

**Overlays over the real background.**
- Cards and charts (stage graphics, 0611) are now proposed for every reel, at most two a minute and only where a
  moment calls for one (`depth.around`, on by default).
- Without the cut-out they are drawn over the footage, not behind the speaker:
  - Cards slide in from the frame edge into the side away from the face, sized to stay clear of the face box.
  - A chart builds in the taller of the free spaces above the face, or between the face and the captions.
  - There is no studio backdrop and no pull-back.

**Editorial cuts.** A new `transitions.style: "editorial"` is the default for new plans (`render/src/editorial.ts`):
- **J-cut.** At every jump cut, the outgoing picture holds for 4 frames, silent, while the next piece's sound
  has already started. The ear leads the eye, which is what makes a cut feel smooth. Each cut keeps a 0.15 s
  pause before the next word, so lips never go out of sync.
  - The hold is skipped where the extra frames don't exist, where they would run into another shot, or where an
    animated transition covers the cut.
- **Alternating punch-in.** Consecutive pieces of the same shot alternate between normal and 1.12x framing about
  the face. The framing resets to normal on a new shot. The 4K source has the pixels for this.
- **Settle.** Where the shot changes (a hard cut in the source, or a jump to another shot), the new shot eases
  from 1.04x to 1x over 0.4 s.
- **B-roll over cuts.** A visual whose edge is within 0.8 s of a jump cut (split panel, B-roll, motion graphic)
  is stretched 0.4 s across it, with its layout span (`hypercut/analyze/cutaways.py`). Without this, the
  speaker comes back for a moment and then jumps.
- **Animated transitions** (0613) are kept, but editorial plans only get the cold-open drop automatically. More
  can be added in the editor or the AI box.

**Alternatives.**
- L-cuts (the incoming picture first while the outgoing sound continues). These would show frames from the cut
  pause, which can hold a filler word with moving lips, so they are not used.
- Crossfades at every cut (`smooth`). These read as soft and amateur on a talking head, so they remain an option
  but are not the default.
- Generating new B-roll for every jump cut. This costs a Claude drawing per cut, so only existing visuals are
  moved.

**Consequences.**
- Reels look like the filmed room by default, and the cut-out (about 15 minutes per minute of video) is no
  longer made unless asked for, so jobs are faster.
- Old plans keep their stored `transitions.style` and backgrounds.
- Old plans that relied on titles behind the speaker without a changed background now show those titles in
  front, off the face.
- Cards are drawn for more reels, which adds one illustrator call per card.
