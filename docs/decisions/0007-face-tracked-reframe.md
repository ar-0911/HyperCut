# 0007: MediaPipe face tracking for the 9:16 crop

Status: accepted, 2026-10-17

**Decision.** Detect the face every few frames with MediaPipe, smooth the track, and store normalized crop
centers as `reframe.keys`. Fall back to a center crop when no face is found.

**Why.** Landscape footage needs a moving crop to keep the speaker in frame, and the same track tells the
renderer where not to put graphics. MediaPipe is fast on CPU and needs no GPU.

**Consequences.** Works best with one speaker. Two people, fast motion or no face (product shots) needs a
smarter tracker later. Vertical source footage mostly skips cropping.
