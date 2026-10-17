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
| [0101](0101-normalize-to-30fps-cfr-h264.md) | Normalize to 30 fps constant frame rate H.264/AAC, 16 kHz mono wav | accepted |
| [0102](0102-ingest-validation-and-errors.md) | Ingest validates with ffprobe and raises IngestError | accepted |
| [0201](0201-backend-selection-and-word-cleanup.md) | Backend selection, lazy imports and word cleanup | accepted |
| [0202](0202-srt-line-grouping.md) | SRT lines are grouped by words, characters, pauses and sentence ends | accepted |
| [0301](0301-presets-and-prompt-to-style.md) | Six presets; prompt-to-style as "closest preset plus a patch" | accepted |
| [0401](0401-analyze-design.md) | Analyze: Claude proposes, code validates and cuts | accepted |
| [0501](0501-reframe-smoothing.md) | Reframe sampling, smoothing and clamping | accepted |
| [0601](0601-render-architecture.md) | Render architecture: one composition, pure logic modules, per-segment video | accepted |
| [0602](0602-crop-zoom-graphic-placement.md) | Crop, zoom and keeping graphics off the face | accepted |
| [0603](0603-captions-and-graphic-templates.md) | Caption animations, graphic templates and fonts | accepted |
| [0604](0604-render-cli-and-browser.md) | Render CLI, serving the video, and finding a browser | accepted |
| [0701](0701-job-server-design.md) | API: file-based jobs, background thread, shared pipeline function | accepted |
| [0801](0801-nextjs-app-and-shared-composition.md) | Web: Next.js client app that imports the render composition | accepted |
| [0802](0802-polling-and-api-contract.md) | Web: polling, and how the browser uses the job API | accepted |
| [0803](0803-client-side-plan-edits.md) | Web: hook choice and transcript edits happen in the browser | accepted |
