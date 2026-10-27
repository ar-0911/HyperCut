# 0024. A visual index of the footage, next to the transcript

Status: accepted (2026-10-26)

## What

A new stage, `hypercut/vision` ("look"), writes `visual_index.json` in the job folder: the source's shots, each
with observations at source timestamps (description, scene type, visible text, objects, people, brightness,
confidence) and the sampled frames under `frames/`. It runs in parallel with transcription, after face tracking
has found the hard cuts. Layers:

1. Shots: `reframe.shots` (the face tracker's hard cuts), else FFmpeg's scene score (> 0.3).
2. Frames: the middle of each shot, plus one per 8 s in long shots, capped at 24 per video, 512 px wide.
3. Local signals: on-screen text through the Tesseract CLI when installed; brightness from FFmpeg.
4. Descriptions through a provider interface (`hypercut/vision/providers.py`): `none` (default), `ollama` (a local
   VLM, default `qwen2.5vl:7b`), or `claude` (frames sent through `llm.ask_json(images=...)` in batches of 8).
   Chosen per video on the upload page ("Understand the footage"), `vision` on `POST /jobs`, or `HYPERCUT_VISION`.

The index is used in three ways:
- **Planning:** the analyze prompt gets one line per shot (type, description, text, objects) with rules: prefer
  hooks the picture supports, and leave shots the speaker points at clear of graphics.
- **Visual relevance:** `keep_footage()` drops drawn full-frame visuals covering most of a shot that shows a
  screen, a product or other footage, and puts that stretch back to the speaker layout, so "look at this" shows
  *this*.
- **Names:** `fix_words()` respells a transcript name (a word capitalized mid-sentence) when the footage writes it
  almost the same way. On the test footage, the bottle reads KACHAVA, so the misheard "Kachaba" becomes "Kachava"
  in 4 places. The edit's "Why this cut" lists each respelling and each shot kept clear.

The index is evidence about the source, kept out of `plan.json` (ADR 0001 unchanged); the plan stays what
HyperCut decided.

## Alternatives

- **Send every frame (or 1 fps) to a model.** On a 3-minute video that is 180+ images for mostly identical
  talking-head frames: slow and costly, with no better decisions. One frame per shot captures what changes.
- **Only local models.** Most private, but a usable VLM is a multi-GB download and slow on a laptop CPU. Ollama
  is supported for people who want that; Claude is the opt-in quality option, since it is already the planner.
- **PySceneDetect / YOLO / PaddleOCR.** Good tools, but heavy dependencies. FFmpeg's scene score plus the face
  tracker's cuts already find hard cuts, and the VLM covers objects and text. Any of them can be added behind the
  same index later.
- **Put observations in the plan.** That would mix evidence with decisions and grow every plan the renderer reads.

## Consequences

- With the default `none`, nothing leaves the machine; shots and frames are still indexed (about 25 s for a 69 s
  4K clip), and scene types stay "unknown" unless Tesseract finds a screen full of text.
- With `claude`, about 3 extra calls per video. On the test footage it described all but the last batch of shots
  correctly (speaker changes, kitchens, a car showroom, the KACHAVA bottle).
- The same index will feed speaker-aware framing, the editing modes and the editing agent (P1/P2).
