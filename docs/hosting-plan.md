# Hosting plan: HyperCut for everyone over the internet

Status: plan, not built. Today HyperCut runs on one computer (see the README's Docker setup and
[ADR 0015](decisions/0015-docker-compose-for-local-use.md)). This document is about giving people a link
they can open instead.

## The question that decides everything: where does the video get processed?

Three things in the pipeline are heavy: transcription (Whisper), face tracking and the speaker cut-out
(MediaPipe), and rendering (HyperFrames driving headless Chrome, about 12 minutes per 50-second reel on 4 CPU
cores). Wherever those run is where the video has to be. That gives three options.

| | A. Everyone runs their own copy | B. Hosted page, local engine | C. Fully hosted service |
|---|---|---|---|
| What people do | Install Docker, run one command | Open your website, install a small engine once | Open your website |
| Where the video is | Their computer | Their computer | Your servers |
| Privacy | Full | Full: only the web page is hosted | You hold their footage; needs a privacy policy, retention, deletion |
| Claude | Their subscription or key | Their subscription or key | Your API key; you pay per reel |
| Your running cost | $0 | About $0 (static hosting) | Fixed $25 to $60 a month plus $0.40 to $1.70 per reel |
| Work to build | Done (this PR) | Small to medium | Large |
| Weak spot | Setup, updates by hand | Still an install step; Safari needs extra work | Cost, abuse, data responsibility |

**Recommendation.** Build B next. It is the only way to have a link people open *and* keep their footage off
your servers, and it costs nearly nothing to run. Do C only once you want paying users, and charge for it,
because every reel costs real money in Claude and compute.

## Can a hosted app keep data local?

Yes, in two ways, and only one is practical now.

1. **Hosted page plus a local engine (option B).** The web page is just HTML and JavaScript; it doesn't have
   to talk to a server you own. Served from your domain, it can talk to the HyperCut engine running on the
   visitor's own computer at `http://localhost:8000`. The upload goes from their browser to their own machine.
   Your server never sees a frame.
2. **Everything inside the browser.** Whisper (transformers.js with WebGPU), MediaPipe (has a web build),
   FFmpeg (ffmpeg.wasm) and a WebCodecs encoder for the HyperFrames page all have browser versions, so in
   principle nothing needs installing. In practice it is a rewrite of every stage in TypeScript, a 3-minute
   4K clip strains browser memory, rendering is slower than native, and Claude can only be reached with the
   user's own API key pasted into the page (a subscription cannot be used from a browser). Worth revisiting
   later, not now.

## Option B in detail: hosted page, local engine

```
 visitor's browser                         visitor's computer
 ┌───────────────────────────┐   fetch     ┌──────────────────────────────┐
 │ hypercut.app (your site)  │ ──────────► │ HyperCut engine :8000         │
 │ Next.js, static files     │ ◄────────── │ api + pipeline + renderer     │
 └───────────────────────────┘  localhost  │ media/ stays here             │
        ▲ served by Vercel/Netlify         └──────────────┬───────────────┘
        │ (no user data)                                  │ transcript text only
                                                          ▼
                                                   Claude (their account)
```

**What changes in the code**

- Web: build the Next.js app as a static export (`output: 'export'`) with the API address read at runtime,
  default `http://localhost:8000`, and a friendly "engine not running, here's how to start it" screen when the
  engine doesn't answer. Host it on Vercel or Netlify (free tier is enough).
- API: add the hosted domain to `HYPERCUT_WEB_ORIGINS`, and answer Chrome's Private Network Access preflight
  with `Access-Control-Allow-Private-Network: true` (Chrome asks before a public site may call `localhost`).
- Browsers: Chrome, Edge and Firefox allow an `https://` page to call `http://localhost`. Safari blocks it as
  mixed content. Fixes, in order of effort: tell Safari users to use Chrome; have the engine serve HTTPS on
  localhost with a locally trusted certificate; or ship the engine as a desktop app (below).
- Security: an engine on `localhost` must refuse requests from other websites. Keep the CORS allow-list to
  your own domain, bind to `127.0.0.1` only, and add a per-install pairing token the page stores after the
  first visit.

**Making the engine easy to install**

1. Publish the Docker image to GitHub Container Registry from CI, so people pull it instead of building it
   (no 10-minute build, no git clone): a two-line `docker-compose.yml` they download from the website.
2. Later, a desktop app (Tauri or Electron) that bundles the engine and shows a tray icon, so nobody installs
   Docker. This is the "no setup at all" end state and also fixes Safari, because the app can open its own
   window instead of relying on the hosted page.

**Cost to you:** a domain (about $12 a year) and free static hosting. Each person's Claude usage is on their
own subscription or key, which is also what the subscription terms require (a subscription is for the
subscriber's own use).

## Option C in detail: fully hosted service

```
 browser ─► Next.js (Vercel) ─► API (container) ─► queue (Redis) ─► workers (CPU containers)
                │                    │                                  │  whisper, mediapipe,
                │ presigned upload   │ auth, jobs, limits                │  claude (API), render
                ▼                    ▼                                  ▼
          object storage (R2 / S3), files deleted after 7 days    Claude API, Deepgram (optional)
```

**Pieces**

| Piece | Choice | Why |
|---|---|---|
| Web | Next.js on Vercel | What the app already is |
| Auth | Clerk or Auth.js with Google sign-in | Needed to tie jobs, limits and billing to a person |
| API | The existing FastAPI app in a container (Fly.io, Railway or Cloud Run) | Same code, plus auth and storage |
| Uploads and outputs | Cloudflare R2 or S3, presigned uploads straight from the browser, lifecycle rule deleting files after 7 days | Large files shouldn't pass through the API; deletion limits what you hold |
| Job queue | Redis (Upstash) with a worker process, replacing FastAPI background tasks | Jobs survive restarts and scale across machines |
| Workers | The same Docker image with 4 vCPU and 8 GB, scaled by queue length (Cloud Run jobs or Fly machines) | Whisper and rendering are CPU-heavy and bursty |
| Transcription | Local Whisper on the worker, or Deepgram for speed | Whisper costs only CPU time |
| Claude | `HYPERCUT_LLM=api` with your Anthropic key | A subscription can't serve other people |
| Billing | Stripe, with a free allowance and paid reel packs | Every reel costs money |

**What changes in the code**

- `api/jobs.py`: a storage interface (local folder today, R2/S3 when hosted) and a `user_id` on every job;
  every endpoint checks the job belongs to the caller.
- `api/main.py`: auth middleware, upload size and duration limits before processing, per-user rate limits,
  render queue instead of the in-process semaphore.
- Workers: download inputs from storage, run the existing stage functions unchanged, upload outputs.
- Renderer: either keep CPU workers, or move to HyperFrames' AWS Lambda or Cloud Run rendering for fast parallel renders.
- Licensing: the renderer, HyperFrames, is Apache 2.0, so hosting needs no renderer licence (ADR 0032).

**Cost estimate per reel** (3-minute input, about 50-second output; rough, check current prices):

| Item | Estimate |
|---|---|
| Claude Opus 5.5 ($4 / $20 per million input / output tokens): style, analysis, visuals director, illustrations | $0.30 to $1.50 (illustrations are most of it; Sonnet 5.5 roughly halves it) |
| Transcription | About $0.01 of CPU with Whisper, or $0.013 with Deepgram |
| Face tracking, cut-out (only when asked for), render: about 15 to 20 CPU-minutes on 4 vCPU | $0.10 to $0.20 |
| Storage and bandwidth (a few hundred MB kept 7 days) | Under $0.01 |
| **Total** | **About $0.40 to $1.70** |

Fixed costs: Vercel Pro $20 a month once it is a commercial site, a small always-on API container $5 to $15,
Redis and auth on free tiers at first, plus a domain. With 100 reels a month that is roughly $65 to $200 a
month in total, almost all of it Claude.

**Privacy in a hosted service.** The footage is on your servers, so: encrypt storage at rest, delete
uploads and renders automatically (7 days, or right after download if the user asks), never use footage for
anything else, write a privacy policy that says this, and offer "delete my data". Anthropic doesn't train on
API data by default. The local option (B) stays available for people who don't want their footage
uploaded at all.

## Suggested order

1. Publish the Docker image to GitHub Container Registry from CI (helps option A today and is step one of B).
2. Option B: static web build with a runtime API address, Private Network Access header, pairing token,
   "start your engine" screen; host the page on Vercel.
3. Desktop app wrapping the engine, so people don't need Docker.
4. Option C only when there are paying users: auth, storage, queue, workers, billing, in that order.

Each step needs its own decision record when it is built (ADR numbers below 0100 for cross-cutting work,
0701+ for the API, 0801+ for the web app).
