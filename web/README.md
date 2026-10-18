# web

Next.js 14 UI for HyperCut: upload, job progress, then a timeline editor for the finished reel (drag, trim,
delete, add text and graphics, import your own clips and pictures, ask AI to edit), live preview, render and
download. See `docs/decisions/0801-*` to `0804-*` and the Web paragraph of `docs/architecture.md`.

```
cd web && npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev   # http://localhost:3000
npm test                                                # vitest + production build
```

The preview imports the composition from `../render/src`, so `render/` must stay importable as source.
The API allows CORS from `HYPERCUT_WEB_ORIGINS` (default `http://localhost:3000`).

To re-edit a reel made with the CLI, import its folder as a job: `python -m api.import_job <folder> [--plan plan.json]`.
