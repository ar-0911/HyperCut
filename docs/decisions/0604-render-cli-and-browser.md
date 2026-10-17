# 0604: Render CLI, serving the video, and finding a browser

Status: accepted, 2026-10-17

**Decision.** `npm run render -- --plan <plan.json> --video <file> --out <mp4>` runs `scripts/render.ts`
(tsx + `@remotion/bundler` + `@remotion/renderer`). It validates and default-fills the plan with
`normalizePlan`, hard-links the video (copy if cross-device) into a temporary public dir, bundles with that
dir, passes `videoSrc` as a `staticFile` name, and renders H.264 to `--out`. Optional `--concurrency`,
`--composition`. Chromium: `REMOTION_BROWSER` if set; else a Chromium under `PLAYWRIGHT_BROWSERS_PATH` or
`/opt/pw-browsers`; else Remotion's own download. WebGL is software (`swiftshader`) so it works headless.
Dependencies are pinned exactly (Remotion 4.0.250) and `package-lock.json` is committed.

**Alternatives.** Symlinking the video (the bundler copies the public dir and drops the link: 404s);
starting our own HTTP server; `file://` URLs (blocked in headless Chromium); `remotion render` CLI (cannot
create the temp public dir or take plan files as props cleanly).

**Why.** The API stage needs one command that takes files and produces a file; hard links make the video
available without copying a 3-minute upload.

**Consequences.** `videoSrc` in props is either a public-dir name or an `http(s)/blob/data` URL, so the web
preview can pass an object URL. The plan's `source.path` is informational; the CLI trusts `--video`.
Renders were verified on a synthetic 1920x1080 clip with all six graphics, cuts, a cold open and zooms.
