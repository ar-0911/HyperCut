# 0804: Web: a timeline editor for re-editing the finished reel

Status: accepted, 2026-10-18

**Decision.**
- The job page becomes a small video editor: a bin (Add, Media, Hook, Captions tabs), the live preview, an
  inspector and an "Ask AI to edit" box, then a toolbar and a timeline with six tracks: Visuals, Overlays,
  Layout, Zooms, Video, Captions.
- The timeline is in REEL time (what you watch). Blocks map to plan entries through the renderer's
  `buildTimeline`; something inside a cold-open hook shows twice and both copies move together, because the
  plan stores one source span for both.
- Editing: drag to move, drag edges to trim, snap to word starts and block edges, drag anything from the bin
  onto the timeline (or click it to add at the playhead), Delete, Duplicate, Split the clip at the playhead,
  undo/redo, Restore original. Removed blocks from the pipeline's plan appear in the bin and drag back in.
  Visual blocks switch between split screen and full screen in the inspector by rewriting the layout under
  them. Caption lines delete as a block; words are fixed in the Captions tab.
- All edits are pure functions in `web/lib/timeline.ts` (unit-tested); `web/lib/history.ts` is the undo
  stack. A drag updates the preview live and records one undo step when released.
- Built by hand with React and CSS; no timeline library.

**Alternatives.** A timeline library such as `@xzdarcy/react-timeline-editor` (drag and zoom for free, but
it models one time axis per row and knows nothing about cut source time, cold-open copies or snapping to
words, which is most of the work here; and a dependency for a few hundred lines). Editing in source time (no
mapping, but what you drag would not match what you see). Moving clips around on the Video track (reordering
segments): left out, cut and trim cover the common case.

**Consequences.** The preview is free and live; only Render costs time (about 12 minutes for a 52 s reel on 4
CPUs). Very short blocks get narrow at low zoom; the + / − buttons zoom the timeline. The editor is a desktop
layout; it stacks on narrow screens but drag-and-drop needs a mouse or trackpad (clicking a bin tile adds at
the playhead instead).
