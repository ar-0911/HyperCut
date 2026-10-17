# web

Next.js 14 UI for HyperCut: upload, job progress, hook picker, editable transcript, live preview, render and download.
See `docs/decisions/0801-*` to `0803-*` and the Web paragraph of `docs/architecture.md`.

```
cd web && npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev   # http://localhost:3000
npm test                                                # vitest + production build
```

The preview imports the composition from `../render/src`, so `render/` must stay importable as source.
The API must allow CORS from the web origin.
