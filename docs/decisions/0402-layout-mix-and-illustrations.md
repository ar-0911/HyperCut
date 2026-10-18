# 0402: Analyze mixes layouts per beat and draws original illustrations

Status: accepted, 2026-10-17

**Decision.**
- Analyze can direct the visuals (`visuals=True`, on by default in `run_pipeline`). Code splits the
  played speech into beats of 2-4.5 s, breaking at sentence ends. Beats tile the kept source time with no
  gaps.
- One director call picks a layout per beat: `speaker`, `split` (speaker in the bottom half, a visual above)
  or `visual` (the visual fills the frame while the speaker keeps talking). For split and visual beats it
  writes an illustration brief tied to what is said, or picks a text card (`kinetic_text`, `stat_card`,
  `list_build`). This call may use web search, so a named brand, product or place is drawn the way it
  really looks. The search is for reference only: nothing is downloaded and no logo or photo is copied.
- Illustrator calls (3 briefs each, 4 in parallel) return flat-vector SVG. Its top-level groups are its
  animation layers, in reveal order. Code parses and sanitizes the SVG with a tag and attribute allowlist
  (no scripts, styles, images, foreign objects, event handlers or external URLs) and stores
  `{viewBox, defs, layers, title}` as an `illustration` graphic. A failed drawing falls back to the
  title as kinetic text, or to the speaker.
- Code enforces the mix: no visual-only first beat, no two visual-only beats in a row, visual-only under
  30% of played time. Text graphics from the main analyze call that would share the panel with a visual
  are dropped; lower thirds, emoji bursts and progress bars stay.

**Alternatives.** Stock or web photos (the cloud environment blocks image hosts, and the user wants
original art to keep the video authentic). AI image generation (paid API, slow, and its raster output
can't be animated layer by layer). A fixed split screen for the whole video (the user asked for a mix).

**Why.** SVG costs nothing extra on the Claude subscription. It stays crisp at any size, and its layers
can be animated frame-exactly in Remotion. Splitting direction from drawing keeps each call focused, and
the drawing calls run in parallel. Web search makes the briefs specific without needing network access
to image hosts.

**Consequences.** A video now costs about 2 + beats/3 Claude calls instead of 2, and the illustrator calls
dominate the analyze time. Drawing quality depends on Claude's SVG. A bad drawing can be re-drawn by
re-running the illustrator on the brief, which is kept in its props.
