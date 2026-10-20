# 0016: Stock footage and generated pictures and clips

Status: accepted, 2026-10-20

**Context.** Adi wants visuals specific to what is said and production grade, and asked how to link image and
video generating AI into HyperCut after looking at Cardboard (research note:
`/mnt/project-files/research/cardboard-and-generative-ai.md`). Cardboard sources real B-roll from stock libraries
and public archives with credits; reportedly it does not generate video. Until now every HyperCut visual was drawn by
Claude as SVG or a 3D scene. Adi cares about running cost and keeps user data local.

**Decision.**
- A visual can come from one of four sources, chosen per moment by analyze (0404): a drawing (as before), stock
  footage, a generated still, or a generated clip (motion moments only).
- The plan carries the request, not the file: `props.generate = {kind: "stock" | "image" | "video", query or
  prompt, media, look, seed}` on a `media` (or `motion`) graphic. No schema change: `props` is free-form, so
  older readers ignore it and the renderer shows nothing until `src` is set.
- A new step, `hypercut/generate/` (`generate(plan, job_dir)`, `python -m hypercut.generate`), runs after analyze,
  before every render and on demand from the editor. It saves `gen-<hash>.<ext>` in the job folder and fills
  `src`, `kind`, `duration` and, for stock, `credit`, `credit_url`, `credit_required`.
- Stock: Pexels and Pixabay (free keys, free commercial licences) and, opt-in without a key, Wikimedia Commons
  photos limited to public domain, CC0 and CC BY. CC BY credits are drawn on screen. Claude looks at the
  thumbnails (new `images=` on `ask_json`) and picks the shot that shows the brief, or none.
- Generation: one hosted aggregator, fal.ai (`FAL_KEY`), so one key covers many models; defaults FLUX.2 Pro for
  stills and Kling 2.1 image-to-video for clips, overridable by env. A clip is always made from a generated
  still, so it matches the reel's look line. Local alternative: `HYPERCUT_GEN_LOCAL=1` runs Z-Image-Turbo and
  Wan 2.2 TI2V 5B (both Apache 2.0) through diffusers on a CUDA GPU.
- Off by default: analyze only offers the sources this machine can fetch (`generate.available()`), so with no
  keys nothing changes. Never a hard requirement, like the Claude API key.
- Cost control: every paid call is checked against `HYPERCUT_GEN_BUDGET_USD` (default $2 per video) in
  `generate.json`; results are cached by request so re-renders don't pay again; a failed call is refunded.
- Failure never breaks the edit: a picture or footage that can't be fetched becomes a drawn illustration of its
  brief (or its title as text); a motion moment keeps its 3D scene, which is always designed as the fallback.
- Prompts ask for no text, logos, real people or faces; titles stay in Remotion where they are sharp.

**Alternatives.** Replicate as the aggregator (similar; fal has the models we want and a simple queue API).
Direct vendor APIs (one integration per model). Local only (most users have no 16-24 GB GPU; the cloud session
has none). Generating the speaker or re-styling footage (breaks "speaker pixels are never regenerated").

**Consequences.** Typical cost about $0.20 per reel for stills plus about $0.30 per generated clip; stock is
free. Only search words and prompts leave the machine. The default model ids are fal's at the time of writing
and should be checked when a key is first used; they are settings, not code. The local backend is untested here
(no GPU in the cloud session).
