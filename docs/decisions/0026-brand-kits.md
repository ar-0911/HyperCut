# 0026. Brand kits: one look and one set of brand files, reused on every reel

Status: accepted (2026-10-26)

## What

A brand kit is a folder, `media/kits/<id>/`, holding `kit.json` and its files:

- **look:** the `caption`, `graphics` and `transitions` parts of a style (fonts, colours, caption animation, theme,
  how cuts look). Pacing, zooms, effects and the editing mode are not in a kit: they are how a reel is *edited*
  (ADR 0025), and one kit should work for a podcast clip and a product demo alike.
- **logo:** an image in a corner (size, opacity), inside the platforms' safe margins.
- **music:** an audio file looped under the whole reel, dipping under speech by itself (`duck`, the share kept
  while someone speaks; 0.12 s down, 0.5 s back up), faded in and out with the reel. Speech is read from the word
  timings, so there is no audio analysis.
- **end card:** a line (a call to action) with the logo large, rising over the reel's fade to black for its last
  seconds.
- **font:** a TTF/OTF/WOFF file registered under a family name, which the captions then use.

`plan.brand` (additive schema field) records what is on a reel, with the files copied into the job as
`brand-<hash>.<ext>`, so a project keeps working if its kit is changed or deleted. Kits are made in the editor's
Brand tab ("Save this look as a kit…", which keeps the current edit's look) or `POST /kits`, chosen on the upload
page or `kit` on `POST /jobs`, put on an edit later with `POST /jobs/{id}/kit` (a new version), and adjusted per
reel in the Brand tab or by the assistant (`brand` op: "move the logo bottom left", "music quieter").

## Alternatives

- **Intro and outro clips that lengthen the reel.** A short that doesn't open on its hook loses viewers in the first
  second, and extra time before the reel shifts every time mapping (captions, checks, export validation). The end
  card goes over the last seconds instead; an intro can come later as an option if asked for.
- **Recipes as kits.** Recipes (ADR 0018) save a whole style, edit settings included, and stay for that. A kit is
  the brand part only, plus files.
- **A bundled music library.** Licences differ per track and a library is large; the user brings music they have
  rights to, and the kit form says so.
- **Audio-based ducking (sidechain compression in FFmpeg).** Needs a second render pass and isn't visible in the
  browser preview; ducking from word timings is the same in both.

## Why

Adi's product note asks for brand kits (fonts, colours, caption style, logo or watermark, intro/outro, music,
transitions) reused across projects. Keeping the kit to the look and brand files makes it composable with modes and
recipes, and copying files into the job keeps projects self-contained (needed for portable projects next).

## Consequences

- Loudness normalization (ADR 0616) runs after the render, so music never pushes the reel past -14 LUFS.
- The kit's font replaces the caption font; the bundled fonts stay for everything else.
- A kit's look overwrites the reel's caption and colour edits when applied; it is a new version, so Undo brings
  them back.
