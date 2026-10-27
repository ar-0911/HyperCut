"""Retakes: a line said again, or a sentence started and restarted, keeps only the last take (ADR 0405).

    retakes(transcript) -> [Retake(start=3.1, end=7.9, kept_at=8.2, text="so the first thing"), ...]

People recording themselves stop and say a line again. The transcript shows it as the same sentence twice in a
row, or a sentence that breaks off and starts over. The last take is usually the one they meant, so the earlier
ones are cut, together with the stumble between the takes. Code only, from word timings: no Claude call.
Conservative on purpose: a phrase repeated for emphasis far apart, or a short line said twice, stays.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from hypercut.plan import Transcript, Word

SENTENCE_END = re.compile(r"[.!?…][\"')\]]*$")
MIN_WORDS = 4  # shorter lines repeat on purpose ("No. No.")
SAME = 0.8  # word-level similarity above which two sentences are the same line
FALSE_START = 3  # words a broken-off start needs to share with the next sentence's opening
MAX_GAP = 8.0  # seconds from the end of one take to the start of the next; further apart is a callback, not a retake


@dataclass
class Retake:
    start: float  # the earlier take, source seconds
    end: float  # up to where the kept take starts
    kept_at: float
    text: str


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9']", "", text.lower())


def sentences(words: list[Word]) -> list[list[Word]]:
    out: list[list[Word]] = []
    current: list[Word] = []
    for w in words:
        current.append(w)
        if SENTENCE_END.search(w.text.strip()):
            out.append(current)
            current = []
    if current:
        out.append(current)
    return out


def _tokens(sentence: list[Word]) -> list[str]:
    return [t for t in (_norm(w.text) for w in sentence) if t]


def _is_retake(earlier: list[str], later: list[str]) -> bool:
    if len(earlier) >= MIN_WORDS and len(later) >= MIN_WORDS and SequenceMatcher(None, earlier, later).ratio() >= SAME:
        return True
    # A false start: broken off, and the next sentence begins the same way.
    n = len(earlier)
    return FALSE_START <= n < len(later) and later[:n] == earlier


def _restart(sentence: list[Word]) -> int:
    """How many opening words are said twice in a row inside one sentence ("so the thing so the thing is"), or 0."""
    tokens = [_norm(w.text) for w in sentence]
    for n in range(len(tokens) // 2, FALSE_START - 1, -1):
        if tokens[:n] == tokens[n:2 * n] and all(tokens[:n]):
            return n
    return 0


LOOKAHEAD = 2  # a take may be followed by a stumble ("sorry, again") before the line is said again
STUMBLE = 3  # words at most in what is said between two takes


def retakes(transcript: Transcript) -> list[Retake]:
    """Earlier takes to cut, in source order."""
    words = sorted(transcript.words, key=lambda w: w.start)
    found: list[Retake] = []
    lines = sentences(words)
    for i, a in enumerate(lines):
        n = _restart(a)
        if n:
            found.append(Retake(start=a[0].start, end=a[n].start, kept_at=a[n].start,
                                text=" ".join(w.text for w in a[:n]).strip()))
        for k, b in enumerate(lines[i + 1:i + 1 + LOOKAHEAD]):
            if b[0].start - a[-1].end > MAX_GAP:
                break
            if k and len(_tokens(lines[i + k])) > STUMBLE:
                break  # something real was said in between: a callback, not a retake
            if _is_retake(_tokens(a), _tokens(b)):
                found.append(Retake(start=a[0].start, end=b[0].start, kept_at=b[0].start,
                                    text=" ".join(w.text for w in a).strip()))
                break
    return sorted(found, key=lambda r: r.start)
