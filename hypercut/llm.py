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

DEFAULT_API_MODEL = "claude-opus-5-5"


class LLMError(RuntimeError):
    pass


def ask_json(prompt: str, system: str = "", timeout: float = 300) -> dict:
    """Send a prompt and return the JSON object Claude answers with."""
    backend = os.environ.get("HYPERCUT_LLM", "cli")
    if backend == "cli":
        text = _ask_cli(prompt, system, timeout)
    elif backend == "api":
        text = _ask_api(prompt, system, timeout)
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


def _ask_cli(prompt: str, system: str, timeout: float) -> str:
    exe = shutil.which("claude")
    if not exe:
        raise LLMError("the `claude` CLI is not installed; install Claude Code or set HYPERCUT_LLM=api")
    cmd = [exe, "-p", prompt, "--output-format", "json"]
    if system:
        cmd += ["--append-system-prompt", system]
    if model := os.environ.get("HYPERCUT_MODEL"):
        cmd += ["--model", model]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise LLMError(f"claude -p failed ({proc.returncode}): {proc.stderr.strip()[:2000]}")
    envelope = json.loads(proc.stdout)
    if envelope.get("is_error"):
        raise LLMError(f"claude -p error: {envelope.get('result')}")
    return envelope.get("result", "")


def _ask_api(prompt: str, system: str, timeout: float) -> str:
    try:
        import anthropic
    except ImportError as e:
        raise LLMError("HYPERCUT_LLM=api needs `pip install anthropic`") from e
    client = anthropic.Anthropic(timeout=timeout)
    kwargs = {"system": system} if system else {}
    with client.messages.stream(
        model=os.environ.get("HYPERCUT_MODEL", DEFAULT_API_MODEL),
        max_tokens=64000,
        messages=[{"role": "user", "content": prompt}],
        **kwargs,
    ) as stream:
        message = stream.get_final_message()
    if message.stop_reason == "refusal":
        raise LLMError("Claude declined the request")
    return "".join(b.text for b in message.content if b.type == "text")
