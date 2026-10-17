# 0103: Ingest caps the normalized video at 1920 pixels tall

Status: accepted, 2026-10-17

**Decision.** Ingest scales any source taller than 1920 pixels down to 1920 tall, keeping the aspect ratio
(4K landscape becomes 3414x1920; 4K vertical becomes 1080x1920). Smaller sources are left alone.

**Alternatives.** Keep full resolution (the first real-footage run); scale everything to 1080p.

**Why.** The output is always a 1080x1920 reel, and a full-height 9:16 crop of a 1920-tall frame is exactly
1080x1920, so pixels above that are thrown away at render time anyway. Keeping 4K made a 16-second render take
about 5 minutes. Scaling to 1080p would upscale the crop and soften it.

**Consequences.** Every stage after ingest (reframe, render) works on at most 1920-tall frames.
