import pytest

from hookline.llm import LLMError, extract_json


def test_extract_fenced():
    assert extract_json('here you go\n```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_bare():
    assert extract_json('sure: {"a": {"b": 2}} done') == {"a": {"b": 2}}


def test_extract_invalid():
    with pytest.raises(LLMError):
        extract_json("no json here")
