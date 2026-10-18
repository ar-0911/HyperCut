# 0015: Docker Compose for running HyperCut locally

Status: accepted, 2026-10-18

**Decision.** One `Dockerfile` (Ubuntu 24.04 with Node 22, Python 3.12, FFmpeg, the MediaPipe and headless
Chrome system libraries, Claude Code, every optional Python extra, the renderer's Chrome downloaded at build
time, and a production build of the web app) and a `docker-compose.yml` that runs that image twice: `api`
(uvicorn, port 8000) and `web` (`next start`, port 3000). Settings come from `.env` (template:
`.env.example`). Uploads and outputs are a bind mount of `./media`; Whisper and MediaPipe models live in a
named volume so they download once. Both ports are bound to `127.0.0.1`. For the Claude subscription backend
the container reads `CLAUDE_CODE_OAUTH_TOKEN`, made with `claude setup-token` (which can run inside the
container, so the host needs nothing but Docker).

**Alternatives.** Manual install only (README steps; still documented for development); a desktop app
(Tauri or Electron; much more work, kept for later in `docs/hosting-plan.md`); separate images for api and web
(smaller web image, but two builds and the web app imports `render/src` anyway); a Debian `node` base image
(Ubuntu packages are what the pipeline was tested with, and Node is copied from the official image either
way); mounting `~/.claude` for the subscription login (doesn't work on macOS, where the login lives in the
Keychain).

**Why.** People should be able to run HyperCut without installing Python, Node, FFmpeg, MediaPipe's GL
libraries and a headless Chrome by hand, while their footage stays on their own disk. Docker is the one
install that covers Mac, Windows and Linux. One image with every backend means switching Claude or
transcription is a `.env` edit, not a rebuild. Binding to localhost keeps a home install from being reachable
on the network.

**Consequences.** The image is large (a few GB) and the first build takes about 10 minutes; publishing it to a
registry from CI would remove the build step (first item in the hosting plan). Inside Docker, Whisper runs on
CPU only. The web app has the API address baked in at build time (`NEXT_PUBLIC_API_URL`), so a different
address means a rebuild. The container runs as uid 1000, so on Linux `media/` must exist (or be owned by uid
1000) before the first start.
