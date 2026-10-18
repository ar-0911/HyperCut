# 0901: Speaker cut-out for green-screen effects, only when asked

Status: accepted, 2026-10-18

**Decision.** A new optional stage, `hypercut/matte`, cuts the speaker out of the normalized video with
MediaPipe's selfie segmentation models and writes `matte.webm` (VP9 with alpha, frame for frame with
`normalized.mp4`). The plan gets `style.depth` (`enabled`, default `background`, `behind_titles`),
`backgrounds` (time spans of `original | blur | dim | color | gradient | media`, with `parallax`) and a
`layer: "front" | "behind"` on every graphic; all additive with defaults, so old plans render as before.

The effects are **off unless the user asks** (Adi, 2026-10-18): the style prompt has to ask for something
behind the speaker, a changed background or a depth/green-screen look (Claude decides, and a keyword check
overrules it if the prompt never mentions anything of the kind), or the user turns them on in the editor (AI
box, Style tab, or "Behind the speaker" on a graphic). Only then is the cut-out made: during the pipeline
in parallel with analyze, or on demand through `POST /jobs/{id}/matte`, or at render time.

How the cut-out is made:
- Two models on a 640 px wide copy: the multi-class model gives a clean silhouette but drops held objects
  (a book vanished in the test), the plain selfie model keeps them but bleeds into busy backgrounds. The
  selfie model's pixels are added only inside the convex hull of the multi-class silhouette.
- Only the person at the reframe's main face is kept, so the montage's other people stay in the background.
- The mask is averaged with the previous frame's (weight 0.6 on the new one) unless the overlap drops below
  0.6, which marks a hard cut, so edges don't flicker and cuts don't smear.
- Python only handles the small frames: FFmpeg decodes a scaled copy, and a second FFmpeg merges the
  upscaled mask with the untouched full-size frames (`alphamerge`) and encodes with libvpx-vp9 in realtime
  mode. About 4.5 minutes for the 69 s 4K test montage on 4 CPUs (36 s for 8 s), 33 MB.

**Alternatives.**
- Robust Video Matting: the best video matting (hair, no flicker) but GPL-3.0, and its weights are not on
  Hugging Face. Adi wants permissively licensed models so HyperCut can be sold.
- BiRefNet (MIT): sharper edges, but seconds per frame on CPU (an hour per clip). A later upgrade for
  stretches that replace the background.
- RMBG 1.4 / 2.0: non-commercial licences.
- A grey mask video composited in the browser: CSS can't use a video as a mask; a pre-merged alpha video
  is what Remotion's `OffthreadVideo transparent` and Chrome's `<video>` both play.
- Generating a 3D speaker: it would regenerate the speaker's pixels, which ADR 0001 rules out.

**Why.** Free, local, allowed by the cloud network policy (storage.googleapis.com), Apache-2.0, and good
enough: text behind the speaker hides edge errors completely (the cut-out sits on the same pixels), and
blurred or dimmed backgrounds forgive soft hair edges.

**Consequences.** Hair edges are soft and very busy backgrounds can leak a little, which shows most with
solid-colour backgrounds. Held objects outside the body's outline (an arm stretched out) may be cut off. The
matte doubles disk use per job (about 0.5 MB per second of video). Renders with the effects decode a second,
transparent video on the frames that need it, so they are slower there.
