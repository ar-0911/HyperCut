# HyperCut renderer

Turns an edit plan (`schema/edit_plan.schema.json`) plus the normalized source video into a 1080x1920 mp4 with
[HyperFrames](https://github.com/heygen-com/hyperframes) (HTML rendered to video in headless Chrome, Apache 2.0).
The editor's preview plays the same page with HyperFrames' player. See `docs/decisions/0032-*`.

```
npm ci
npx hyperframes browser ensure  # the headless Chrome HyperFrames drives (or set HYPERCUT_BROWSER)
npm test                        # vitest: time mapping, layout, captions, frame runtime, dry run
npm run typecheck
npm run render -- --plan plan.json --video normalized.mp4 --out out/final.mp4 [--overlays 1] [--keep DIR]
```

`--keep DIR` leaves the HyperFrames project there (`index.html`, `assets/`, `frames/`); `npx hyperframes
preview DIR` then opens it in HyperFrames' own editor.

How a render works (`scripts/render.ts`):

1. A dry run (`src/collect.tsx`) draws every frame once, without a page, and lists the video frames and the
   sound the reel uses.
2. FFmpeg extracts exactly those frames into `frames/` (frame-exact video, no seeking a `<video>` element).
3. `index.html` (`src/hf/html.ts`) holds the plan, the sound as HyperFrames `<audio>` clips with volume
   envelopes, and the page script `dist/hypercut-page.js` (`src/hf/page.tsx`, built by `npm run build`).
4. `hyperframes render` seeks the page frame by frame; on each seek the page draws that frame with the React
   components and holds it until pictures, fonts and the 3D scene are ready. HyperFrames mixes and encodes.

HyperFrames' anonymous usage reporting is always turned off (`HYPERFRAMES_NO_TELEMETRY=1`).

Layout: `src/frame.tsx` (the frame runtime the components are written against: current frame, sequences,
freezes, springs, video, audio), `src/frame-three.tsx` (three.js drawn once per frame), `src/timing.ts`
(source <-> output time), `src/layout.ts` (crop, zoom, graphic placement), `src/captions.ts` (lines and
animations), `src/HyperCut.tsx` (the reel), `src/Captions.tsx`, `src/Graphics.tsx`, `src/Motion.tsx` (3D),
`src/theme.ts`. Design records: `docs/decisions/0601-*` onward and `0032-*`.
