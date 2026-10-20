"""One way to ask Claude for JSON, shared by every stage.

Backends:
- "cli" (default): Claude Code headless (`claude -p`), on the user's own
  Claude subscription. For personal use; no API key needed.
- "api": the Anthropic API, for when other people use the app.
  Needs `pip install anthropic` and ANTHROPIC_API_KEY.

Pick with HYPERCUT_LLM=cli|api. HYPERCUT_MODEL overrides the model.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

DEFAULT_API_MODEL = "claude-opus-5-5"


class LLMError(RuntimeError):
    pass


def ask_json(prompt: str, system: str = "", timeout: float = 300, web_search: bool = False,
             images: list[str | Path] | None = None) -> dict:
    """Send a prompt and return the JSON object Claude answers with.

    `web_search` lets Claude search the web first (for reference only; nothing is downloaded).
    `images` are local picture files (jpg/png/webp) Claude looks at, in order, before the prompt; they are
    numbered from 0 in the order given.
    """
    backend = os.environ.get("HYPERCUT_LLM", "cli")
    images = [Path(p) for p in images or []]
    if backend == "cli":
        text = _ask_cli(prompt, system, timeout, web_search, images)
    elif backend == "api":
        text = _ask_api(prompt, system, timeout, web_search, images)
    else:
        raise LLMError(f"unknown HYPERCUT_LLM backend: {backend!r}")
    return extract_json(text)


def extract_json(text: str) -> dict:
    """Parse the first JSON object in text, tolerating ```json fences."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else text[text.find("{") : text.rfind("}") + 1]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise LLMError(f"Claude did not return valid JSON: {e}\n---\n{text[:2000]}") from e
    if not isinstance(value, dict):
        raise LLMError("expected a JSON object")
    return value


def _ask_cli(prompt: str, system: str, timeout: float, web_search: bool = False, images: list[Path] | None = None) -> str:
    exe = shutil.which("claude")
    if not exe:
        raise LLMError("the `claude` CLI is not installed; install Claude Code or set HYPERCUT_LLM=api")
    tools = ["WebSearch"] if web_search else []
    if images:
        # Claude Code looks at pictures through its Read tool: list the files and let it read only those folders.
        listing = "\n".join(f"{i}: {p.resolve()}" for i, p in enumerate(images))
        prompt = f"First look at each of these image files with the Read tool, in order:\n{listing}\n\n{prompt}"
        tools.append("Read")
    cmd = [exe, "-p", prompt, "--output-format", "json"]
    for folder in sorted({str(p.resolve().parent) for p in images or []}):
        cmd += ["--add-dir", folder]
    if system:
        cmd += ["--append-system-prompt", system]
    if model := os.environ.get("HYPERCUT_MODEL"):
        cmd += ["--model", model]
    if tools:
        cmd += ["--allowedTools", ",".join(tools)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise LLMError(f"claude -p failed ({proc.returncode}): {proc.stderr.strip()[:2000]}")
    envelope = json.loads(proc.stdout)
    if envelope.get("is_error"):
        raise LLMError(f"claude -p error: {envelope.get('result')}")
    return envelope.get("result", "")


def _ask_api(prompt: str, system: str, timeout: float, web_search: bool = False, images: list[Path] | None = None) -> str:
    try:
        import anthropic
    except ImportError as e:
        raise LLMError("HYPERCUT_LLM=api needs `pip install anthropic`") from e
    client = anthropic.Anthropic(timeout=timeout)
    kwargs: dict = {"system": system} if system else {}
    if web_search:
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
    with client.messages.stream(
        model=os.environ.get("HYPERCUT_MODEL", DEFAULT_API_MODEL),
        max_tokens=64000,
        messages=[{"role": "user", "content": _content(prompt, images or [])}],
        **kwargs,
    ) as stream:
        message = stream.get_final_message()
    if message.stop_reason == "refusal":
        raise LLMError("Claude declined the request")
    return "".join(b.text for b in message.content if b.type == "text")


_MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}


def _content(prompt: str, images: list[Path]) -> str | list[dict]:
    """The user turn for the API: the pictures (base64), each labelled with its number, then the prompt."""
    if not images:
        return prompt
    import base64

    blocks: list[dict] = []
    for i, p in enumerate(images):
        media_type = _MEDIA_TYPES.get(p.suffix.lower())
        if media_type is None:
            raise LLMError(f"unsupported image type: {p.name}")
        blocks.append({"type": "text", "text": f"Image {i}:"})
        blocks.append({"type": "image", "source": {"type": "base64", "media_type": media_type,
                                                   "data": base64.b64encode(p.read_bytes()).decode()}})
    blocks.append({"type": "text", "text": prompt})
    return blocks
