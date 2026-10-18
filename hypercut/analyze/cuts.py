"""Deterministic cutting: filler words and dead air become removed ranges.

Nothing here calls Claude. Cuts come from word timings and, when a wav is
given, FFmpeg's `silencedetect`.
"""

from __future__ import annotations

import re
import shutil
import subprocess

from hypercut.plan import Segment, Transcript

FILLERS = {"um", "umm", "uh", "uhh", "uhm", "er", "erm", "ah", "hmm", "hm", "mm", "mmm"}
MIN_PIECE = 0.15  # kept pieces shorter than this are dropped as glitches
MIN_CUT = 0.25  # a pause is only cut if this much goes: a smaller jump cut saves no time and looks choppy

Range = tuple[float, float]


def is_filler(text: str) -> bool:
    return re.sub(r"[^a-z]", "", text.lower()) in FILLERS


def detect_silences(wav_path: str, min_duration: float, noise_db: int = -35) -> list[Range]:
    """Silent ranges of at least min_duration seconds; [] if FFmpeg is unavailable."""
    exe = shutil.which("ffmpeg")
    if not exe or min_duration <= 0:
        return []
    proc = subprocess.run(
        [exe, "-hide_banner", "-nostats", "-i", wav_path, "-af",
         f"silencedetect=noise={noise_db}dB:d={min_duration}", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    )
    starts = [float(m) for m in re.findall(r"silence_start: (-?[\d.]+)", proc.stderr)]
    ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", proc.stderr)]
    return [(max(s, 0.0), e) for s, e in zip(starts, ends) if e > s]


def cut_ranges(
    transcript: Transcript,
    duration: float,
    max_silence: float,
    remove_fillers: bool = True,
    silences: list[Range] | None = None,
    keep_pause: float = 0.08,
) -> list[Range]:
    """Ranges of source time to remove, sorted and merged."""
    pad = keep_pause  # breathing room kept around speech
    words = sorted(transcript.words, key=lambda w: w.start)
    cuts: list[Range] = []

    if remove_fillers:
        cuts += [(w.start, w.end) for w in words if is_filler(w.text)]

    # Gaps between words, including before the first and after the last.
    edges: list[Range] = []
    prev_end = 0.0
    for w in words:
        edges.append((prev_end, w.start))
        prev_end = max(prev_end, w.end)
    edges.append((prev_end, duration))
    for i, (a, b) in enumerate(edges):
        if b - a <= max_silence:
            continue
        lo = a + (pad if i > 0 else 0.0)
        hi = b - (pad if i < len(edges) - 1 else 0.0)
        if hi - lo >= MIN_CUT:
            cuts.append((lo, hi))

    # Silence the audio sees but the transcript doesn't (breaths, pauses inside a word's span).
    for s, e in silences or []:
        if e - s > max_silence and e - s - 2 * pad >= MIN_CUT:
            cuts.append((s + pad, e - pad))

    return _merge(cuts)


def _merge(ranges: list[Range]) -> list[Range]:
    merged: list[Range] = []
    for a, b in sorted(ranges):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def subtract(span: Range, cuts: list[Range]) -> list[Range]:
    """The parts of span left after removing cuts (sorted, merged)."""
    pieces: list[Range] = []
    cursor = span[0]
    for a, b in cuts:
        if b <= cursor or a >= span[1]:
            continue
        if a > cursor:
            pieces.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < span[1]:
        pieces.append((cursor, span[1]))
    return [(a, b) for a, b in pieces if b - a >= MIN_PIECE]


def build_segments(
    duration: float,
    cuts: list[Range],
    hook: Range | None,
    strategy: str,
) -> list[Segment]:
    """Output segments: cold_open plays the hook first then the whole body; trim starts the body at the hook."""
    segments: list[Segment] = []
    body_start = 0.0
    if hook and strategy == "trim":
        body_start = hook[0]
    elif hook and strategy == "cold_open":
        segments += [Segment(start=round(a, 3), end=round(b, 3), reason="hook") for a, b in subtract(hook, cuts)]
    segments += [
        Segment(start=round(a, 3), end=round(b, 3), reason="body")
        for a, b in subtract((body_start, duration), cuts)
    ]
    return segments


SENTENCE_END = re.compile(r"[.!?…][\"')\]]*$")
END_TAIL = 0.4  # seconds kept after the last word, so the line lands before the fade


def ending_word(transcript: Transcript, preferred: int | None = None, min_fraction: float = 0.5) -> int | None:
    """Index of the word the reel should end on: `preferred` (Claude's pick) when it ends a sentence in
    the back half, else the last sentence-final word in the back half; None if there is no such word."""
    words = transcript.words
    if not words:
        return None
    floor = words[-1].end * min_fraction
    ok = lambda i: 0 <= i < len(words) and SENTENCE_END.search(words[i].text) and words[i].end >= floor  # noqa: E731
    if preferred is not None and ok(preferred):
        return preferred
    for i in range(len(words) - 1, -1, -1):
        if ok(i):
            return i
    return None


def end_at(segments: list[Segment], transcript: Transcript, word: int) -> list[Segment]:
    """Drop everything played after `word` (plus a short tail, never into the next word)."""
    words = transcript.words
    stop = words[word].end + END_TAIL
    if word + 1 < len(words):
        stop = min(stop, max(words[word].end + 0.05, words[word + 1].start))
    out: list[Segment] = []
    for seg in segments:
        if seg.reason == "hook" or seg.end <= stop:
            out.append(seg)
        elif seg.start < stop - MIN_PIECE:
            out.append(Segment(start=seg.start, end=round(stop, 3), reason=seg.reason))
    return out


def recut(plan, audio_wav: str | None = None):
    """Rebuild `segments` from the plan's own transcript and `style.pacing` (e.g. after changing how much
    pause to keep), keeping the chosen hook, the strategy and where the reel ends. Returns a new plan."""
    from hypercut.plan import EditPlan

    plan = EditPlan.model_validate(plan.model_dump())
    pacing = plan.style.pacing
    body = [s for s in plan.segments if s.reason == "body"]
    old_end = body[-1].end if body else plan.source.duration
    silences = detect_silences(audio_wav, pacing.max_silence) if audio_wav else []
    cuts = cut_ranges(plan.transcript, plan.source.duration, pacing.max_silence, pacing.remove_fillers, silences,
                      keep_pause=pacing.keep_pause)
    hook = plan.hook.candidates[plan.hook.chosen] if plan.hook.candidates else None
    segments = build_segments(plan.source.duration, cuts, (hook.start, hook.end) if hook else None, plan.hook.strategy)
    # Keep the ending: nothing after where the reel stopped, plus the new pause after that last word.
    stop = old_end + max(0.0, pacing.keep_pause - 0.08)
    plan.segments = [
        s if s.reason == "hook" or s.end <= stop else Segment(start=s.start, end=round(stop, 3), reason=s.reason)
        for s in segments
        if s.reason == "hook" or s.start < stop - MIN_PIECE
    ]
    return plan
