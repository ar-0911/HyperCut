# HyperCut

Paste raw footage, get a short. HyperCut transcribes the video, adds animated captions, finds the hook
and opens with it, and drops in motion graphics where the content calls for them, in a style you describe
in a prompt. The speaker is never altered: everything is cuts and overlays.

Status: skeleton. The edit plan schema (`hypercut/plan.py`) and Claude helper are in place; the stages are being built.

```sh
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

- [Architecture](docs/architecture.md): how the pipeline works
- [Decisions](docs/decisions/README.md): every design decision and why
- [CLAUDE.md](CLAUDE.md): conventions and module ownership for agents
