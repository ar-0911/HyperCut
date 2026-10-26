# 0018: Recipes and variants

Status: accepted, 2026-10-20

**Context.** Cardboard lets users save "recipes" and ask for several variants ("3 hooks", "a 30 s cut"). HyperCut
already has style presets and hook candidates.

**Decision.**
- A recipe is a whole saved `Style` with a name, stored in `media/recipes.json` (local, like everything else).
  Save one from the editor's Finish panel; pick one on the upload page. A job started with a recipe uses that
  style as is and skips the style prompt (`run_pipeline(recipe=...)`, `POST /jobs` field `recipe`).
- Variants (`hypercut/variants.py`, `POST /jobs/{id}/variants`): one per other hook candidate (`rehook`, which keeps
  the body's cuts and ending) and 30 s / 45 s cuts (`trim_to`, which ends on the last full sentence that fits).
  Each variant becomes its own job sharing the footage and files (hard links), so it opens and renders in the
  editor like any other. No Claude calls.

**Alternatives.** Recipes as style prompts (Claude would re-read them each time and drift). Variants inside one
job (the editor, the render and downloads all assume one plan per job).

**Consequences.** Recipes live with the media folder; moving machines means copying `recipes.json`. Shorter cuts
drop the end of the video rather than picking the best moments; a smarter "best 30 s" would need Claude.
