# 0704: Endpoints for generation, recipes, variants, review and export

Status: accepted, 2026-10-20

**Decision.**
- `POST /jobs/{id}/generate {plan, graphic_id?, prompt?}` fetches what the plan waits for (or one graphic again) and
  returns the plan unsaved, like the assistant. `GET /jobs/{id}` adds `generation` (spent, budget, available).
- `PUT /jobs/{id}/plan` accepts `gen-*` files that exist in the job folder as well as imports.
- `GET/POST /recipes`, `DELETE /recipes/{name}`; `POST /jobs` takes `recipe`.
- `POST /jobs/{id}/variants` makes new jobs (hard-linked footage and files, `variant_of` in job.json).
- `POST /jobs/{id}/review` needs a finished render; it returns issues and a fixed plan, unsaved.
- `POST /jobs/{id}/export {overlays}` runs in the background (`export` state in job.json) and holds the render slot
  while it renders the overlay track; the zip is served by the files endpoint.
- Rendering fetches pending pictures first (`run.fetch_new_assets`), as it draws new graphics.
