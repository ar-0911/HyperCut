# hookline

Paste raw footage, get a short. hookline transcribes the video, adds animated captions, finds the hook
and opens with it, and drops in motion graphics where the content calls for them, in a style you describe
in a prompt. The speaker is never altered: everything is cuts and overlays.

Status: skeleton. The edit plan schema (`hookline/plan.py`) is in place; the stages are being built.

```sh
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

See [CLAUDE.md](CLAUDE.md) for the architecture and who owns which module.
