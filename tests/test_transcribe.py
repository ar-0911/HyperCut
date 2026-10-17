import json
from types import SimpleNamespace as NS

import pytest

from hypercut import transcribe as tr
from hypercut.plan import Transcript, Word
from hypercut.transcribe.__main__ import main


@pytest.fixture
def wav(tmp_path):
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF")
    return p


class FakeModel:
    def transcribe(self, path, word_timestamps, vad_filter):
        assert word_timestamps
        w = lambda t, s, e, p: NS(word=t, start=s, end=e, probability=p)
        segs = [NS(words=[w(" Hello", 0.0, 0.4, 0.9), w(" world.", 0.5, 0.5, 0.8)]), NS(words=None)]
        return iter(segs), NS(language="en")


def test_whisper_backend(wav, monkeypatch):
    names = []
    monkeypatch.setattr(tr, "_load_whisper_model", lambda n: names.append(n) or FakeModel())
    monkeypatch.setenv("HYPERCUT_WHISPER_MODEL", "tiny")
    monkeypatch.delenv("HYPERCUT_TRANSCRIBE", raising=False)
    t = tr.transcribe(wav)
    assert names == ["tiny"]
    assert [w.text for w in t.words] == ["Hello", "world."]
    assert t.words[1].end > t.words[1].start  # zero-length word repaired
    assert t.words[0].confidence == 0.9


def test_deepgram_backend(wav, monkeypatch):
    words = [
        {"word": "hola", "punctuated_word": "Hola,", "start": 0.1, "end": 0.4, "confidence": 0.99, "speaker": 0},
        {"word": "mundo", "start": 0.5, "end": 0.9, "confidence": 0.95},
    ]
    payload = dict(results=dict(channels=[dict(detected_language="es", alternatives=[dict(words=words)])]))
    monkeypatch.setenv("DEEPGRAM_API_KEY", "k")
    monkeypatch.setattr(tr, "_deepgram_request", lambda p, k: payload if k == "k" else {})
    t = tr.transcribe(wav, "deepgram")
    assert t.language == "es"
    assert [w.text for w in t.words] == ["Hola,", "mundo"]
    assert t.words[0].speaker == "0" and t.words[1].speaker is None


def test_backend_from_env(wav, monkeypatch):
    monkeypatch.setenv("HYPERCUT_TRANSCRIBE", "deepgram")
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    with pytest.raises(tr.TranscribeError, match="DEEPGRAM_API_KEY"):
        tr.transcribe(wav)


def test_errors(wav, tmp_path):
    with pytest.raises(tr.TranscribeError, match="unknown backend"):
        tr.transcribe(wav, "nope")
    with pytest.raises(tr.TranscribeError, match="not found"):
        tr.transcribe(tmp_path / "missing.wav")


def test_clean_fixes_overlap_and_drops_blanks():
    words = tr._clean([
        dict(text="b", start=0.3, end=0.9),
        dict(text=" ", start=0.0, end=0.1),
        dict(text="a", start=0.0, end=0.5),
    ])
    assert [w.text for w in words] == ["a", "b"]
    assert words[1].start >= words[0].end


def _t(*items):
    return Transcript(words=[Word(text=t, start=s, end=e) for t, s, e in items])


def test_srt_format_and_sentence_break():
    srt = tr.to_srt(_t(("Hi", 0.0, 0.3), ("there.", 0.3, 0.8), ("Next", 0.9, 3661.5)))
    assert srt == (
        "1\n00:00:00,000 --> 00:00:00,800\nHi there.\n\n"
        "2\n00:00:00,900 --> 01:01:01,500\nNext\n"
    )


def test_srt_splits_on_gap_and_word_count():
    t = _t(*[(f"w{i}", i * 0.1, i * 0.1 + 0.05) for i in range(7)], ("late", 5.0, 5.2))
    blocks = tr.to_srt(t, max_words=3).strip().split("\n\n")
    assert [b.splitlines()[2] for b in blocks] == ["w0 w1 w2", "w3 w4 w5", "w6", "late"]


def test_srt_empty():
    assert tr.to_srt(Transcript()) == ""


def test_cli(wav, tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "_load_whisper_model", lambda n: FakeModel())
    out, srt = tmp_path / "t.json", tmp_path / "t.srt"
    assert main([str(wav), "--out", str(out), "--srt", str(srt)]) == 0
    assert json.loads(out.read_text())["words"][0]["text"] == "Hello"
    assert "Hello world." in srt.read_text()
    assert main([str(tmp_path / "missing.wav")]) == 1


def test_model_download_failure_names_the_host(monkeypatch):
    import sys
    import types

    from hypercut import transcribe as t

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("403 Forbidden")

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Boom))
    with pytest.raises(t.TranscribeError, match="huggingface.co"):
        t._load_whisper_model("small")


def test_whisper_gets_decoded_samples_for_ingest_wav(tmp_path, monkeypatch):
    import wave

    np = pytest.importorskip("numpy")
    p = tmp_path / "real.wav"
    with wave.open(str(p), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(np.array([0, 16384, -32768], dtype="<i2").tobytes())
    seen = []

    class Model(FakeModel):
        def transcribe(self, audio, word_timestamps, vad_filter):
            seen.append(audio)
            return super().transcribe(audio, word_timestamps, vad_filter)

    monkeypatch.setattr(tr, "_load_whisper_model", lambda n: Model())
    tr.transcribe(p, "whisper")
    assert isinstance(seen[0], np.ndarray) and seen[0].dtype == np.float32
    assert seen[0].tolist() == [0.0, 0.5, -1.0]


def test_whisper_gets_path_for_other_audio(wav, monkeypatch):
    seen = []

    class Model(FakeModel):
        def transcribe(self, audio, word_timestamps, vad_filter):
            seen.append(audio)
            return super().transcribe(audio, word_timestamps, vad_filter)

    monkeypatch.setattr(tr, "_load_whisper_model", lambda n: Model())
    tr.transcribe(wav, "whisper")
    assert seen == [str(wav)]
