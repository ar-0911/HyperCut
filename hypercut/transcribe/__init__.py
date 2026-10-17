"""hypercut.transcribe: wav in, word-timed `Transcript` out, plus SRT export.

Backends: local faster-whisper (default) and Deepgram Nova-3. Pick with the `backend`
argument or HYPERCUT_TRANSCRIBE=whisper|deepgram. Heavy dependencies are imported
inside the functions that use them.
"""

from __future__ import annotations

import os
from pathlib import Path

from hypercut.plan import Transcript, Word

DEFAULT_WHISPER_MODEL = "small"
DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_MODEL = "nova-3"
MIN_WORD = 0.02  # seconds; the plan requires end > start

__all__ = ["transcribe", "to_srt", "TranscribeError"]


class TranscribeError(RuntimeError):
    pass


def transcribe(wav_path: str | Path, backend: str | None = None) -> Transcript:
    """Transcribe `wav_path`. `backend` is "whisper" or "deepgram"; default from the environment."""
    backend = (backend or os.environ.get("HYPERCUT_TRANSCRIBE") or "whisper").lower()
    path = Path(wav_path)
    if not path.is_file():
        raise TranscribeError(f"audio file not found: {path}")
    if backend == "whisper":
        language, raw = _whisper(path)
    elif backend == "deepgram":
        language, raw = _deepgram(path)
    else:
        raise TranscribeError(f"unknown backend {backend!r}; use 'whisper' or 'deepgram'")
    return Transcript(language=language, words=_clean(raw))


def _clean(raw: list[dict]) -> list[Word]:
    """Drop empty words and make timings valid: ordered, non-overlapping, end > start."""
    words: list[Word] = []
    prev_end = 0.0
    for r in sorted(raw, key=lambda r: r["start"]):
        text = str(r["text"]).strip()
        if not text:
            continue
        start = max(float(r["start"]), prev_end, 0.0)
        end = max(float(r["end"]), start + MIN_WORD)
        conf = r.get("confidence")
        words.append(
            Word(
                text=text,
                start=start,
                end=end,
                speaker=r.get("speaker"),
                confidence=None if conf is None else min(max(float(conf), 0.0), 1.0),
            )
        )
        prev_end = end
    return words


# --- faster-whisper -------------------------------------------------------------------------


def _load_whisper_model(name: str):
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise TranscribeError("faster-whisper is not installed: pip install 'hypercut[whisper]'") from e
    return WhisperModel(name, device="auto", compute_type="auto")


def _whisper(path: Path) -> tuple[str, list[dict]]:
    model = _load_whisper_model(os.environ.get("HYPERCUT_WHISPER_MODEL", DEFAULT_WHISPER_MODEL))
    segments, info = model.transcribe(str(path), word_timestamps=True, vad_filter=True)
    raw = [
        {"text": w.word, "start": w.start, "end": w.end, "confidence": w.probability}
        for seg in segments
        for w in (seg.words or [])
    ]
    return getattr(info, "language", None) or "en", raw


# --- Deepgram -------------------------------------------------------------------------------


def _deepgram_request(path: Path, api_key: str) -> dict:
    try:
        import httpx
    except ImportError as e:
        raise TranscribeError("httpx is not installed: pip install 'hypercut[deepgram]'") from e
    params = {"model": DEEPGRAM_MODEL, "smart_format": "true", "punctuate": "true", "detect_language": "true"}
    try:
        resp = httpx.post(
            DEEPGRAM_URL,
            params=params,
            headers={"Authorization": f"Token {api_key}", "Content-Type": "audio/wav"},
            content=path.read_bytes(),
            timeout=300,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise TranscribeError(f"Deepgram request failed: {e}") from e
    return resp.json()


def _deepgram(path: Path) -> tuple[str, list[dict]]:
    api_key = os.environ.get("DEEPGRAM_API_KEY")
    if not api_key:
        raise TranscribeError("DEEPGRAM_API_KEY is not set")
    data = _deepgram_request(path, api_key)
    try:
        channel = data["results"]["channels"][0]
        words = channel["alternatives"][0].get("words", [])
    except (KeyError, IndexError, TypeError) as e:
        raise TranscribeError("unexpected Deepgram response shape") from e
    raw = [
        {
            "text": w.get("punctuated_word") or w["word"],
            "start": w["start"],
            "end": w["end"],
            "confidence": w.get("confidence"),
            "speaker": None if w.get("speaker") is None else str(w["speaker"]),
        }
        for w in words
    ]
    return channel.get("detected_language") or "en", raw


# --- SRT ------------------------------------------------------------------------------------


def _timestamp(t: float) -> str:
    ms = round(t * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(transcript: Transcript, max_words: int = 6, max_chars: int = 42, max_gap: float = 0.8) -> str:
    """Group words into short subtitle lines. A line ends at sentence punctuation, a pause
    longer than `max_gap`, or when it reaches `max_words` / `max_chars`."""
    lines: list[list[Word]] = []
    cur: list[Word] = []
    for w in transcript.words:
        if cur:
            too_long = len(" ".join(x.text for x in cur + [w])) > max_chars
            if len(cur) >= max_words or too_long or w.start - cur[-1].end > max_gap:
                lines.append(cur)
                cur = []
        cur.append(w)
        if w.text.endswith((".", "?", "!")):
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    blocks = [
        f"{i}\n{_timestamp(line[0].start)} --> {_timestamp(line[-1].end)}\n{' '.join(w.text for w in line)}\n"
        for i, line in enumerate(lines, 1)
    ]
    return "\n".join(blocks)
