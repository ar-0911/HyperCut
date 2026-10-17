# 0006: Cold-open hooks by default

Status: accepted, 2026-10-17

**Decision.** Claude scores the transcript for hook strength and returns up to three candidates. By default
the chosen hook (2 to 5 seconds) plays first and the video then plays from the start ("cold open"). The
other strategy, "trim", cuts everything before the hook. The user can pick any candidate in the web app.

**Why.** A cold open keeps the context the speaker built up, which trimming loses. Showing three candidates
covers the cases where the model's top pick isn't the user's.

**Consequences.** Implemented purely as `segments` (the hook span appears twice), so the renderer has no hook
logic. If the footage has no strong line, the best available one is used and its low score is shown.
