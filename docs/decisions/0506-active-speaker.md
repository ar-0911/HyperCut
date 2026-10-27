# 0506: In shots with several people, frame whoever is talking

Status: accepted, 2026-10-26

**Decision.** When a sample has two or more distinct faces, the reframe stage reads each face's jaw opening with
MediaPipe's face landmarker (the `jawOpen` blendshape, on a crop around the face scaled to 256 px). Per shot, faces
are joined into people (nearest position from sample to sample; a person must be in half the shot). A person's
activity is their mean jaw change over one second; whoever is most active (above a small floor) leads. The crop
starts on the first person to talk and moves to someone else only after they have led for 1.5 s, so a "yeah" or a
laugh doesn't flip the frame. The move is a jump marked `switch`, handled like a hard cut by the smoothing (no pan
across the table), and recorded as `reframe.switches` (additive schema field) so "Why this cut" can say "Moved the
frame to the person who started talking". Shots with one person, or without readings, keep the main-face rule
(ADR 0505). Duplicate detections of one face from overlapping tiles are merged first, so single-person footage
never loads the landmarker.

**Alternatives.**
- *Audio diarization (pyannote).* MIT licensed, but its models are gated behind a Hugging Face token, it needs
  PyTorch, and it still doesn't say which face on screen is the voice. Deepgram already fills `Word.speaker` when
  that backend is chosen; joining voices to faces is a later step.
- *Audio-visual active speaker models (TalkNet, Light-ASD).* More accurate on hard cases, but research code with
  PyTorch and non-commercial or unclear licences for some weights.
- *Mouth landmark distance without blendshapes.* Works, but needs per-face normalization; `jawOpen` is already
  normalized 0..1.

**Why.** Adi's note asks for speaker-aware editing and "never show the wrong person during a quote". Lip motion is
local, free, needs no key, and reuses the MediaPipe dependency and model cache the stage already has (one extra
3.8 MB model, fetched once).

**Consequences.** Tested on a two-person clip built from the test footage (each speaker live for 6 s while the other
is a still): the switch lands at 6.0 s. On the single-person montage nothing changes (no switches; 44 of 362
samples had a second face, but none was ever more active than the speaker). Chewing, laughing or a speaker who
barely moves their jaw can mislead it; the floor and the 1.5 s hold limit that. Talking off screen isn't seen.
MediaPipe needs `libegl1` and `libgles2` on Linux; without them, or without the model, the stage logs that active
speaker detection is off and keeps the main face.
