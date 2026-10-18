# HyperCut

Paste raw footage, get a short. HyperCut transcribes the video, adds animated captions, finds the hook
and opens with it, and drops in motion graphics where the content calls for them, in a style you describe
in a prompt. The speaker is never altered: everything is cuts and overlays. You can then re-edit the reel
in a timeline editor in the browser and render a 1080x1920 mp4.

HyperCut runs on your own computer. Your videos stay on your disk; see [Privacy](#privacy-what-leaves-your-computer)
for the two small exceptions. To let other people use it over the internet, see the
[hosting plan](docs/hosting-plan.md).

- [Run it with Docker (recommended)](#run-it-with-docker-recommended)
- [Claude: subscription or API key](#claude-subscription-or-api-key)
- [Transcription: do I need Whisper?](#transcription-do-i-need-whisper)
- [Privacy: what leaves your computer](#privacy-what-leaves-your-computer)
- [Run it without Docker](#run-it-without-docker)
- [Settings](#settings)
- [Troubleshooting](#troubleshooting)
- [Giving it to other people](#giving-it-to-other-people)
- [Development](#development)

## Run it with Docker (recommended)

Docker packs everything HyperCut needs (Python, Node, FFmpeg, Whisper, MediaPipe, the headless Chrome the
renderer uses, Claude Code) into one image, so the only thing to install is Docker itself.

**You need**

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac, Windows with WSL 2) or Docker
  Engine with the Compose plugin (Linux).
- A Claude Pro or Max subscription, or an Anthropic API key. See [below](#claude-subscription-or-api-key).
- About 10 GB of free disk (image, models, renders) and 8 GB of RAM. No GPU needed.

**Steps**

```sh
git clone https://github.com/ar-0911/HyperCut.git hypercut
cd hypercut
cp .env.example .env
mkdir -p media
docker compose build                                # first time only, about 10 minutes
```

Now connect Claude. With a **subscription**, get a long-lived login token (this opens a sign-in link; log in
with your Claude account and copy the token it prints):

```sh
docker compose run --rm api claude setup-token
```

Paste the token into `.env` as `CLAUDE_CODE_OAUTH_TOKEN=...`. With an **API key** instead, set
`HYPERCUT_LLM=api` and `ANTHROPIC_API_KEY=...` in `.env`.

Start it:

```sh
docker compose up -d
```

Open **http://localhost:3000**, upload a video (up to 3 minutes), describe a style, and wait. The first job
also downloads the Whisper model (about 500 MB, once). Finished reels and every job's files are in `media/`.

| To | Run |
|---|---|
| see progress or errors | `docker compose logs -f api` |
| stop | `docker compose down` |
| update to the latest version | `git pull && docker compose up -d --build` |
| change a setting | edit `.env`, then `docker compose up -d` |

Both ports are bound to `127.0.0.1`, so only your own computer can open the app.

## Claude: subscription or API key

Claude writes the edit plan: which moment is the hook, what to cut, where graphics and zooms go, and the
illustrations. It reads the transcript text and your style prompt. It never receives the video.

| | Subscription (`HYPERCUT_LLM=cli`, default) | API key (`HYPERCUT_LLM=api`) |
|---|---|---|
| Cost | Included in Claude Pro or Max | Pay per use, very roughly $0.30 to $1.50 per reel on Claude Opus 5.5 ($4 / $20 per million input / output tokens), most of it the illustrations |
| Limits | Counts toward your plan's usage limits | Your API rate limits |
| Who may use it | Only you. A subscription is for the subscriber's own use, so don't share an install that runs on your subscription | Anyone you let use your install |
| Setup | Docker: `claude setup-token`, put the token in `CLAUDE_CODE_OAUTH_TOKEN`. Without Docker: install Claude Code and log in once | Create a key at [console.anthropic.com](https://console.anthropic.com), set `ANTHROPIC_API_KEY` |

How the subscription works: HyperCut runs Claude Code headless (`claude -p`), the same tool you use in a
terminal, so it uses whatever account Claude Code is logged in to. In Docker there is no browser to log in
with, so Claude Code reads the token from `CLAUDE_CODE_OAUTH_TOKEN` instead. Treat that token like a
password.

`HYPERCUT_MODEL` picks another model on either backend (for example `claude-sonnet-5-5`, half the API price).

## Transcription: do I need Whisper?

You need a transcription backend, because everything else (captions, cuts, the hook) is built on word timings.
You don't need to set anything up for it: local Whisper is the default and is already in the Docker image.

| | Whisper (`HYPERCUT_TRANSCRIBE=whisper`, default) | Deepgram (`HYPERCUT_TRANSCRIBE=deepgram`) |
|---|---|---|
| Where it runs | Your computer ([faster-whisper](https://github.com/SYSTRAN/faster-whisper)) | Deepgram's servers |
| Cost | Free | About $0.013 per 3-minute video |
| Privacy | Audio never leaves your computer | The audio is uploaded to Deepgram |
| Speed (3-minute video, laptop CPU) | 1 to 3 minutes with `small` | Seconds |
| Setup | None. The model downloads from huggingface.co on first use | Get a key at [deepgram.com](https://deepgram.com), set `DEEPGRAM_API_KEY` |

Whisper model size is `HYPERCUT_WHISPER_MODEL`: `tiny` (75 MB, fastest, rough), `base`, `small` (about
500 MB, default), `medium`, `large-v3` (about 3 GB, best, slow on CPU). It uses a GPU automatically when one
is available outside Docker.

## Privacy: what leaves your computer

| Data | Where it goes |
|---|---|
| Your video, audio, frames, renders, imported clips | Nowhere. They stay in `media/` |
| Transcript text, style prompt, AI edit box requests | Claude (Anthropic), to write the plan. Anthropic doesn't train on API or Claude Code data by default |
| Audio | Only if you choose Deepgram |
| Model files (Whisper, MediaPipe) | Downloaded once from huggingface.co and storage.googleapis.com; nothing is uploaded |

When illustrations are on, Claude may run a web search for reference, which sends search terms, not your
media. Nothing is uploaded to a HyperCut server: there isn't one.

## Run it without Docker

Use this for development, or to use a GPU for Whisper.

**You need:** Python 3.10 or newer, Node.js 20 or newer, FFmpeg on your `PATH`, and for the subscription
backend [Claude Code](https://docs.claude.com/en/docs/claude-code) (`npm install -g @anthropic-ai/claude-code`,
then run `claude` once and log in). On Linux, MediaPipe also needs `sudo apt install libegl1 libgles2`.

| OS | Install the basics |
|---|---|
| macOS | `brew install python@3.12 node ffmpeg` |
| Ubuntu / Debian | `sudo apt install python3 python3-venv ffmpeg libegl1 libgles2` and Node 20+ from [nodejs.org](https://nodejs.org) |
| Windows | Use WSL 2 with Ubuntu and follow the Ubuntu line |

```sh
git clone https://github.com/ar-0911/HyperCut.git hypercut && cd hypercut
python3 -m venv .venv
.venv/bin/pip install -e '.[api,whisper,reframe,matte]'   # add ,anthropic for the API key, ,deepgram for Deepgram
(cd render && npm ci)                                     # renderer; downloads a headless Chrome on first render
(cd web && npm ci)
```

Run the job server and the web app in two terminals (settings are environment variables, see [Settings](#settings)):

```sh
.venv/bin/uvicorn api.main:app --port 8000
cd web && NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev    # http://localhost:3000
```

Or skip the web app and use the command line:

```sh
.venv/bin/python -m hypercut.run talk.mp4 --style 'calm, minimal' --render   # writes media/cli-talk/plan.json and output.mp4
.venv/bin/python -m api.import_job media/cli-talk                            # open that run in the editor
```

## Settings

Set these in `.env` (Docker) or as environment variables (without Docker).

| Variable | Default | What it does |
|---|---|---|
| `HYPERCUT_LLM` | `cli` | `cli` = Claude subscription via Claude Code, `api` = Anthropic API |
| `CLAUDE_CODE_OAUTH_TOKEN` | | Subscription token from `claude setup-token` (Docker) |
| `ANTHROPIC_API_KEY` | | API key, for `HYPERCUT_LLM=api` |
| `HYPERCUT_MODEL` | Claude Code's default / `claude-opus-5-5` | Claude model |
| `HYPERCUT_TRANSCRIBE` | `whisper` | `whisper` (local) or `deepgram` (cloud) |
| `HYPERCUT_WHISPER_MODEL` | `small` | `tiny`, `base`, `small`, `medium`, `large-v3` |
| `DEEPGRAM_API_KEY` | | For `HYPERCUT_TRANSCRIBE=deepgram` |
| `HYPERCUT_MEDIA` | `./media` | Where uploads and outputs go |
| `HYPERCUT_CACHE` | `~/.cache/hypercut` | Where MediaPipe models are cached |
| `HYPERCUT_WEB_ORIGINS` | `http://localhost:3000` | Web app origins the API accepts (comma-separated) |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Where the web app finds the API (build time) |
| `REMOTION_BROWSER` | Remotion's own download | Path to a Chrome or Chromium for rendering |

## Troubleshooting

- **"the `claude` CLI is not installed"** (without Docker): install Claude Code, or switch to `HYPERCUT_LLM=api`.
- **"claude -p failed" / "not logged in"**: in Docker, check `CLAUDE_CODE_OAUTH_TOKEN` in `.env` and run
  `docker compose up -d` again; without Docker, run `claude` and log in. If it says you hit a usage limit,
  wait for it to reset or use an API key.
- **"could not load Whisper model"**: the first run needs internet to download the model. Behind a firewall,
  allow huggingface.co and `*.hf.co`, or use Deepgram.
- **Permission denied writing `media/`** (Linux): the container runs as user 1000. Run `mkdir -p media`
  before the first `docker compose up`, or `sudo chown -R 1000 media`.
- **The web page can't reach the API**: the job server must be on port 8000. If you changed the port or
  host, rebuild with `NEXT_PUBLIC_API_URL` set and add the web address to `HYPERCUT_WEB_ORIGINS`.
- **Rendering is slow**: about 12 minutes for a 50-second reel on 4 CPU cores is normal. Give Docker Desktop
  more CPUs (Settings, Resources) to speed it up.

## Giving it to other people

The simplest private option: they clone this repo and follow [Run it with Docker](#run-it-with-docker-recommended)
with their own Claude subscription or API key. Their videos never touch your machine or a server.

For a link anyone can open, read the [hosting plan](docs/hosting-plan.md). It compares hosting only the web
page while each person's video is processed on their own computer (still private) against a fully hosted
service (you store their videos and pay for Claude and compute).

## Development

```sh
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q          # Python tests (no Claude, no models, no network)
(cd render && npm test)                # renderer tests
(cd web && npm test)                   # web tests + production build
```

- [Architecture](docs/architecture.md): how the pipeline works
- [Decisions](docs/decisions/README.md): every design decision and why
- [Hosting plan](docs/hosting-plan.md): options for running HyperCut for everyone over the internet
- [CLAUDE.md](CLAUDE.md): conventions and module ownership for agents
