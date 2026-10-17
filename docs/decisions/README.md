# Decision records

Each file records one decision: what we chose, what else we considered, and why. Numbers below 0100 are
project-wide; each stage has its own range (ingest 01xx, transcribe 02xx, style 03xx, analyze 04xx, reframe
05xx, render 06xx, api 07xx, web 08xx). Add a new file
when a decision changes rather than rewriting history, and mark the old one "Superseded by NNNN".

| # | decision | status |
|---|---|---|
| [0001](0001-edit-plan-is-the-contract.md) | The edit plan JSON is the only contract between stages; Claude never edits pixels | accepted |
| [0002](0002-input-and-output-limits.md) | Up to 3 minutes in, 15 to 60 seconds of 1080x1920 out | accepted |
| [0003](0003-claude-via-subscription.md) | Claude through Claude Code on the user's subscription, API as an option | accepted |
| [0004](0004-local-whisper-transcription.md) | Local faster-whisper by default, Deepgram optional | accepted |
| [0005](0005-remotion-rendering.md) | Render with Remotion | accepted |
| [0006](0006-cold-open-hooks.md) | Cold-open hooks by default, with the top three to choose from | accepted |
| [0007](0007-face-tracked-reframe.md) | MediaPipe face tracking for the 9:16 crop | accepted |
| [0008](0008-local-web-app.md) | Local web app: FastAPI + Next.js, files on disk | accepted |
| [0009](0009-build-with-braid.md) | Build in parallel with braid | accepted |
| [0010](0010-deferred-features.md) | What we are deliberately not building yet | accepted |
