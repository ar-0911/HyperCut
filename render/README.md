# HyperCut renderer

Remotion 4 project that turns an edit plan (`schema/edit_plan.schema.json`) plus the normalized source
video into a 1080x1920 mp4.

```
npm ci
npm test                      # vitest: time mapping, layout, captions, schema guard
npm run typecheck
npm run render -- --plan plan.json --video normalized.mp4 --out out/final.mp4
npm run studio                # preview in Remotion Studio (uses schema/examples/sample_plan.json)
```

Set `REMOTION_BROWSER=/path/to/chrome` to use a specific Chromium.

Layout: `src/timing.ts` (source <-> output time), `src/layout.ts` (crop, zoom, graphic placement),
`src/captions.ts` (lines and animations), `src/HyperCut.tsx` (composition), `src/Captions.tsx`,
`src/Graphics.tsx`, `src/theme.ts`, `scripts/render.ts` (CLI). Design records: `docs/decisions/0601-*` to
`0604-*`.
