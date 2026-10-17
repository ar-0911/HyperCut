# 0801: Web: Next.js client app that imports the render composition

Status: accepted, 2026-10-17

**Decision.**
- `web/` is Next.js 14 (App Router, TypeScript) with React 18.3.1 and Remotion 4.0.250, the same versions as
  `render/`. Every page is a client component; there is no server code, so the app is just a UI for the API.
- The API address is `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).
- The preview is `@remotion/player` playing `HyperCut` imported from `../render/src/HyperCut` through the
  `@render/*` alias (`externalDir: true` in `next.config.mjs`, `paths` in `tsconfig.json`). The composition is
  not copied, so the preview and the final render cannot drift. Types come from `@render/plan`.
- `web/` and `render/` each have their own `node_modules`. `webpack.resolve.modules` puts `web/node_modules`
  first so React and Remotion resolve to one copy even when `render/node_modules` exists (two Reacts break
  hooks). Aliasing `react` itself broke Next's server build, so lookup order is used instead.
- The player reads `normalized.mp4` from the API's files endpoint (the file the renderer uses too).
- Plain CSS with light and dark variables, no UI library.

**Alternatives.** Copying the composition into `web/` (drift). A shared npm workspace package (cleaner, but it
restructures `render/`, which another task owns). Server components or route handlers proxying the API (more code,
and CORS is not an issue for a local app). Tailwind or a component kit (more dependencies for six screens).

**Consequences.** Anything exported from `render/src` that the preview imports must stay browser-safe (no
Node APIs). `render/` must stay importable as source. The API must allow cross-origin requests from the web
origin; this is flagged in ADR 0802.
