# 0603: Caption animations, graphic templates and fonts

Status: accepted, 2026-10-17

**Decision.**
- *Lines.* Words are grouped `words_per_line` at a time, breaking early after sentence-ending punctuation
  and after pauses over 0.7 s. A line shows from its first word until 0.25 s after its last (or until the
  next line starts).
- *Animations.* `karaoke`: whole line visible, current word highlighted. `pop`: like karaoke, and the
  current word punches in from 60% with overshoot over 0.18 s. `typewriter`: words appear as spoken and
  stay. `bounce`: words drop in from above with overshoot as spoken. Easing is a hand-written
  ease-out-back, not Remotion's `spring`, so the state is a pure function of time and unit-tested.
- *Templates.* All six `GraphicType`s have a React template reading `props` (`kinetic_text.text`;
  `stat_card.value`/`label`, numeric values count up; `emoji_burst.emoji`/`count`; `list_build.items`;
  `lower_third.title`/`subtitle`; `progress_bar` fills across its span). Missing props fall back to
  sensible defaults rather than failing. Look comes from `graphics.theme` (`clean`, `bold`, `playful`,
  `cinematic`) and `accent_color` via `theme.ts`.
- *Fonts.* Font stacks name the style's font first, then Montserrat/Inter/Arial; nothing is downloaded at
  render time. Emoji use the system color-emoji font. Randomness is never used (emoji burst is a
  deterministic fan-out), so a frame renders identically every time.
- A test checks that `GRAPHIC_TYPES` and caption animations match the generated JSON schema, so a schema
  change cannot silently leave a type unrendered.

**Alternatives.** `@remotion/google-fonts` (needs network at render); Remotion `spring`; one generic
graphic with a `kind` switch.

**Why.** Offline, deterministic rendering matters more than exact typography in an MVP; fonts can be
bundled later by dropping files into `public/` and a `@font-face`.

**Consequences.** On a machine without Montserrat the fallback is used (the sandbox render looks right but
not identical to a machine with the font). `lower_third` needs `title` (or `text`); unknown template props
are ignored.
