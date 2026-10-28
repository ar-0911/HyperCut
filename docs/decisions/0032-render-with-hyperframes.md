# 0032. Render and preview with HyperFrames instead of Remotion

Status: accepted (2026-10-27). Supersedes [0005](0005-remotion-rendering.md).

## What

The reel is now a HyperFrames composition: one HTML page that HyperFrames (heygen-com/hyperframes, Apache 2.0,
npm `hyperframes`, pinned at 0.8.207) renders to video in headless Chrome, and that the editor plays with
HyperFrames' own player. Remotion is gone from `render/` and `web/`.

The look is unchanged because the components are unchanged. HyperCut's layers (`HyperCut.tsx`, captions,
graphics, stage, effects around the speaker, 3D motion moments, brand) were already pure functions of the frame
number, so they keep their React code and run on a small frame runtime instead of Remotion:

- `render/src/frame.tsx` gives the components what they used from Remotion: the current frame, `Sequence`,
  `Freeze`, `AbsoluteFill`, `Img`, `interpolate`, `spring` (closed-form damped spring, retimed by
  `durationInFrames`), `OffthreadVideo` and `Audio`, `staticFile`, `delayRender`. `frame-three.tsx` draws the
  three.js scene once per frame (react-three-fiber with no loop of its own).
- `render/src/hf/page.tsx` is the page script. HyperFrames calls it on every seek (the `hf-seek` protocol: every
  frame of a render, every tick or scrub of the player); it draws that frame and holds it until its pictures,
  fonts and 3D scene are ready.
- Video is drawn frame-exact, never by seeking a `<video>`: a dry run (`render/src/collect.tsx`) draws every
  frame once without a page and lists the frames of each file the reel shows; `scripts/render.ts` extracts
  exactly those with FFmpeg (JPEG, PNG with alpha for the speaker cut-out), and in a render each video is an
  `<img>` of its frame. In the editor's preview it is a muted `<video>` kept in step with the player.
- Sound comes from the same dry run: what each frame plays (file, position, rate, volume) is joined into
  HyperFrames `<audio>` clips with volume envelopes (`data-automation`), so cut easing, J-cuts, fades and
  music ducking are mixed by HyperFrames exactly as the components ask. Looping music is split at its length.
- `render/src/hf/html.ts` builds the page in Node (the render) and in the browser (the editor). The editor
  (`web/components/Preview.tsx`) puts it in `<hyperframes-player srcdoc>`, sends later edits to the page as
  messages (the picture changes in place), and rebuilds the page only when the sound or length changes,
  returning to the same time. `Preview` offers the calls the timeline already used (`seekTo`,
  `getCurrentFrame`, `toggle`, `isPlaying`, frame events), so the timeline, the on-screen list and the
  shortcuts are untouched.

`npm run render -- --plan --video --out [--overlays 1]` keeps its interface, so `hypercut.run.render_plan`, the
API and the export are unchanged. `--overlays 1` is HyperFrames' transparent MOV (ProRes 4444). `--keep DIR`
leaves the HyperFrames project for `npx hyperframes preview DIR`. HyperFrames' anonymous usage reporting is
always off (`HYPERFRAMES_NO_TELEMETRY=1`, `DO_NOT_TRACK=1`), in the script and in the Docker image.

## Alternatives

- **Rewrite every component as HTML with GSAP timelines**, the way HyperFrames is usually written. It is the
  native style and lets HyperFrames' Studio edit the parts, but it is a rewrite of about 2,650 lines of tuned
  look, with every regression that brings. The frame runtime keeps the look exact and still leaves room for
  new graphics as GSAP scenes or catalogue blocks inside the same page.
- **Let HyperFrames play the footage as its own `<video>` clips.** Tested: a clip must exist when the page loads
  and must not move in the page, while ours appear and disappear with segments, freezes and layouts. A clip
  moved in the page left a copy of its frame behind. Extracting frames ourselves keeps every component free.
- **Keep Remotion for the preview only.** Fewer moving parts in the editor, but two renderers that can drift
  apart, and Remotion's licence still applies.

## Consequences

- No renderer licence: Remotion needs a paid company licence above 3 people; HyperFrames is Apache 2.0.
- What the editor plays is the page the render draws, made by the same code.
- A render first extracts the frames it needs: about 75 s and ~350 MB of temporary JPEGs for a 56-second reel of
  1920-high footage on 4 cores, then about 10 minutes of capture. The test reel rendered in 14 minutes
  while another render ran on the same 4 cores.
- Checked on a fresh plan of the test footage (split and visual layouts, illustrations, cards, lower thirds, a
  3D motion moment, a whip cut): every layer draws, the QA checks pass (size, fps, length, A/V sync, no black
  or frozen frames, -14.3 LUFS), and the speech is within a frame of the source in every segment.
- HyperFrames is at 0.8.x and moves fast. It is pinned to an exact version and upgraded on purpose.
- `npm run render` builds the page script first (esbuild, about 2 s); the web app copies it, the player and the
  HyperFrames runtime into `public/hf` before `dev` and `build` (`web/scripts/hf-assets.mjs`).
- Chrome: `HYPERCUT_BROWSER` (or the old `REMOTION_BROWSER`), else a Playwright Chromium, else the one
  `npx hyperframes browser ensure` installs.
