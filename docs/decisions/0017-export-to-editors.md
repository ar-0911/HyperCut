# 0017: Export to Final Cut, Resolve and Premiere

Status: accepted, 2026-10-20

**Context.** Cardboard exports XML to the big editors so a professional can finish the edit. Adi wants HyperCut
to be usable by other people, some of whom will want to finish in their own tool.

**Decision.**
- `hypercut/export.py` (`export(job_dir)`, `python -m hypercut.export`, `POST /jobs/{id}/export`) writes
  `media/<job>/export/` and `hypercut-export.zip` with: `timeline.fcpxml` (FCPXML 1.10: Final Cut, Resolve),
  `timeline.xml` (FCP7 xmeml 5: Premiere, Resolve), `captions.srt` at reel time, `footage.mp4`, `overlays.mov`
  and a README.
- Track 1: every kept piece in order as plain cuts, scaled to fill 9:16 and shifted to the speaker's average
  position in that piece (from `reframe`).
- Track 2: the graphics and captions rendered alone on transparency as ProRes 4444 (`render --overlays 1`, the
  composition's new `overlaysOnly` prop). This carries every HyperCut graphic without re-implementing it.
- Not carried as edits: zooms and punch-ins, animated transitions, J-cuts and the speed change. The README says so.
- Media paths are absolute file URLs to the export folder (HyperCut runs on the user's machine); moving the
  folder means relinking, which every editor offers.

**Alternatives.** OpenTimelineIO (another dependency and adapter quality varies; the two XML formats cover all
three editors). EDL (no reframing, no second track). Rebuilding graphics as titles in each editor (huge, and they
would not match).

**Consequences.** The overlay render takes about as long as a normal render. Clip framing uses each editor's
transform units, which differ; the README asks the editor to check framing after import.
