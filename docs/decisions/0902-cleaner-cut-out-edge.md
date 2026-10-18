# 0902: A cleaner cut-out edge: MODNet hair, snapped to the picture

Status: accepted, 2026-10-18

**Context.** With the speaker over a drawn scene or a studio backdrop (ADR 0611), Adi could see the cut-out's
outline. There were three causes:
- MediaPipe works at 256 px, so its edge was blobby and carried chunks of the old background, mostly around hair.
- The mask was scaled up 3-6x without looking at the picture, so the edge never followed real hair or shoulders.
- The renderer's drop shadow (36 px blur at 45 %) spread above the head and read as a dark rim.

**Decision.**
- **Hair.** MODNet portrait matting (Apache-2.0, ONNX from huggingface.co/Xenova/modnet, run with onnxruntime,
  512 px short side) draws a real alpha matte with hair strands.
- **Who the speaker is.** MediaPipe still decides which person is the speaker and where the body is. MODNet's
  matte is kept only near that person and is filled with MediaPipe's solid body (`with_hair`), because MODNet
  alone missed a seated speaker's lap and chair and caught the edges of other people.
- **Snapping the edge.** A guided filter (He et al., radius 6 at 1280 px) snaps the alpha to the edges of the
  frame itself. A short opacity ramp (0.2 to 0.85) then trims the faint rim of old background
  (`snap_edge`). Without MODNet (no onnxruntime, or the download fails) the same snapping runs on the
  MediaPipe mask.
- **Resolution.** The alpha is now made at 1280 px wide instead of 640, and VP9 encodes it at crf 30 instead
  of 34, so edges stay crisp.
- **Smoothing.** The hair matte is averaged with the previous frame's within a shot, like the mask, so strands
  don't flicker.
- **Shadow.** The drop shadow under the speaker is now lower and fainter (30 px down, 40 px blur, 30 %).

**Alternatives.**
- **Snapping only:** 0.04 s per frame. It removed the background chunks and was the biggest single gain, but
  hair still had a cut-paper edge. It remains the fallback.
- **MODNet alone:** its hair was the best, but it dropped body parts.
- **BiRefNet (MIT):** sharper still, but seconds per frame on CPU.
- **Robust Video Matting:** GPL-3.0. RMBG: non-commercial. Both are ruled out as in ADR 0901.
- **Light wrap or edge blur in the renderer:** CSS can't blur only the edge of a video with alpha. A cleaner
  matte fixes the cause instead.

**Consequences.**
- The cut-out takes about 3x longer: 0.42 s per frame on 4 CPUs, about 14 minutes for the 69 s test montage,
  up from 4.5. It still runs only when green-screen effects are asked for, and in parallel with analyze.
- The first run downloads a 25 MB model from huggingface.co.
- Matte files grow a little because of the lower crf.
- The speaker's own pixels are still untouched; only the alpha changed.
