# 0005: Render with Remotion

Status: accepted, 2026-10-17

**Decision.** The renderer is a Remotion (React) project in `render/` that takes `plan.json` and the
normalized video.

**Alternatives.** FFmpeg with ASS subtitles plus a Python compositor (MoviePy); After Effects templates.

**Why.** Motion graphics and caption animations are far easier to build and iterate as React components
with frame-exact timing, and the web app can preview the plan with the same components. FFmpeg alone is
simpler to start but its graphics top out quickly.

**Consequences.** The project has a Node side. Remotion is free for individuals and companies of up to 3
people; a larger company needs a Remotion license.
