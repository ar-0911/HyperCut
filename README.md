# HyperCut

Paste raw footage, get a short. HyperCut transcribes the video, adds animated captions, finds the hook
and opens with it, and drops in motion graphics where the content calls for them, in a style you describe
in a prompt. The speaker is never altered: everything is cuts and overlays.

Status: skeleton. The edit plan schema (`hypercut/plan.py`) and Claude helper are in place; the stages are being built.

```sh
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

Quickstart (needs FFmpeg; `cd render && npm ci` once for rendering):

```sh
.venv/bin/pip install -e '.[dev,api,whisper,reframe]'
.venv/bin/python -m hypercut.run talk.mp4 --style 'calm, minimal' --render   # no server: plan.json + output.mp4
.venv/bin/uvicorn api.main:app --port 8000                                    # or run the job server
curl -F video=@talk.mp4 -F style='bold and punchy' localhost:8000/jobs        # -> {"id": ...}
curl localhost:8000/jobs/<id>                                                 # status, stage, plan
curl -X POST localhost:8000/jobs/<id>/render; curl -O localhost:8000/jobs/<id>/files/output.mp4
```

- [Architecture](docs/architecture.md): how the pipeline works
- [Decisions](docs/decisions/README.md): every design decision and why
- [CLAUDE.md](CLAUDE.md): conventions and module ownership for agents
