import pytest

from hypercut.llm import LLMError, extract_json


def test_extract_fenced():
    assert extract_json('here you go\n```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_bare():
    assert extract_json('sure: {"a": {"b": 2}} done') == {"a": {"b": 2}}


def test_extract_invalid():
    with pytest.raises(LLMError):
        extract_json("no json here")


def test_images_reach_the_cli_through_its_read_tool(monkeypatch, tmp_path):
    import json
    import subprocess

    from hypercut import llm

    img = tmp_path / "f.jpg"
    img.write_bytes(b"jpg")
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"result": '{"ok": 1}'}), "")

    monkeypatch.setenv("HYPERCUT_LLM", "cli")
    monkeypatch.setattr(llm.shutil, "which", lambda name: "/bin/claude")
    monkeypatch.setattr(llm.subprocess, "run", fake_run)
    assert llm.ask_json("look", images=[img]) == {"ok": 1}
    cmd = seen["cmd"]
    assert str(img.resolve()) in cmd[2] and cmd[cmd.index("--allowedTools") + 1] == "Read"
    assert cmd[cmd.index("--add-dir") + 1] == str(tmp_path.resolve())


def test_images_reach_the_api_as_base64_blocks(tmp_path):
    from hypercut import llm

    img = tmp_path / "f.png"
    img.write_bytes(b"png")
    blocks = llm._content("which?", [img])
    assert blocks[0] == {"type": "text", "text": "Image 0:"} and blocks[1]["source"]["media_type"] == "image/png"
    assert blocks[-1] == {"type": "text", "text": "which?"} and llm._content("x", []) == "x"
