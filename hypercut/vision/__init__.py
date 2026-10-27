"""hypercut.vision: what is on screen in the source, and when (ADR 0024).

    build_index(mp4, source, reframe, job_dir, provider="none") -> VisualIndex   # also writes visual_index.json

The transcript says what is said; the visual index says what is shown. Four layers, cheapest first:

1. Shots: the hard cuts face tracking already found (`reframe.shots`), else FFmpeg's scene score.
2. Frames: one representative frame per shot (its middle), more for long shots, capped (`MAX_FRAMES`) and
   downscaled to 512 px, each keeping its source timestamp. Never every frame.
3. Local signals: on-screen text with Tesseract when it is installed; frame brightness and how much it changes.
4. Descriptions from a vision-language model behind a provider interface (`hypercut.vision.providers`):
   "none" (default: nothing leaves the machine and nothing is downloaded), "ollama" (a local model) or
   "claude" (frames are sent to Claude, so it is opt-in and the UI says so).

The index is evidence about the SOURCE and is kept out of the edit plan: the plan says what HyperCut decided,
the index says what it saw. The analyze stage reads a compact summary of it (`summary()`), and
`keep_footage()` stops a drawn visual from covering a shot that already shows what is being said (a screen
recording, a product). Without an index everything works as before, from the transcript alone.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from hypercut.plan import Reframe, Source

INDEX_FILE = "visual_index.json"
FRAMES_DIR = "frames"
MAX_FRAMES = 24
LONG_SHOT = 8.0  # shots longer than this get a frame every LONG_SHOT seconds
FRAME_WIDTH = 512
SCENE_THRESHOLD = 0.3

# What a shot mostly shows. talking_head: a person talking to camera. screen: a screen recording, app or slide.
# product: an object being shown. b_roll: other footage (a place, an activity). text: a title card or caption.
SceneType = Literal["talking_head", "interview", "screen", "product", "b_roll", "text", "unknown"]
# Shots that show something themselves: a drawn visual must not cover them.
SHOWING = ("screen", "product", "b_roll")


class Observation(BaseModel):
    t: float = Field(ge=0)  # source seconds
    frame: str  # file name under frames/
    description: str = ""
    scene_type: SceneType = "unknown"
    visible_text: list[str] = []
    objects: list[str] = []
    people: int | None = None  # how many people are visible, when known
    brightness: float | None = None  # 0..1 mean luma
    confidence: float = Field(default=0.0, ge=0, le=1)


class Shot(BaseModel):
    id: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    observations: list[Observation] = []

    @property
    def scene_type(self) -> str:
        """The most confident type among the shot's observations."""
        typed = [o for o in self.observations if o.scene_type != "unknown"]
        return max(typed, key=lambda o: o.confidence).scene_type if typed else "unknown"


class Correction(BaseModel):
    t: float  # source seconds of the word
    heard: str
    written: str


class VisualIndex(BaseModel):
    version: Literal[1] = 1
    duration: float
    provider: str = "none"
    shots: list[Shot] = []
    # Transcript words respelled the way the footage writes them (`fix_words`).
    corrections: list[Correction] = []

    def at(self, t: float) -> Shot | None:
        return next((s for s in self.shots if s.start <= t < s.end), None)


def load(path: str | Path) -> VisualIndex | None:
    path = Path(path)
    return VisualIndex.model_validate_json(path.read_text()) if path.is_file() else None


def save(index: VisualIndex, path: str | Path) -> None:
    Path(path).write_text(index.model_dump_json(indent=2) + "\n")


# Layer 1: shots

def scene_cuts(mp4: str | Path, threshold: float = SCENE_THRESHOLD) -> list[float]:
    """Source times where FFmpeg's scene score jumps (a hard cut); [] without FFmpeg."""
    exe = shutil.which("ffmpeg")
    if not exe:
        return []
    res = subprocess.run(
        [exe, "-hide_banner", "-nostats", "-i", str(mp4), "-an", "-vf",
         f"scale=320:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True, timeout=900,
    )
    return [round(float(t), 3) for t in re.findall(r"pts_time:([\d.]+)", res.stderr)]


def shots_from_cuts(cuts: list[float], duration: float, min_len: float = 0.5) -> list[tuple[float, float]]:
    edges = [0.0] + sorted(c for c in cuts if min_len <= c <= duration - min_len) + [duration]
    spans = []
    for a, b in zip(edges, edges[1:]):
        if spans and b - a < min_len:
            spans[-1] = (spans[-1][0], b)
        elif b > a:
            spans.append((a, b))
    return spans


# Layer 2: frames

def sample_times(shots: list[tuple[float, float]], cap: int = MAX_FRAMES) -> list[tuple[int, float]]:
    """(shot index, source time) to look at: each shot's middle, plus one every LONG_SHOT s in long shots,
    thinned evenly to `cap` (every shot keeps its middle while the cap allows)."""
    mids = [(i, round((a + b) / 2, 3)) for i, (a, b) in enumerate(shots)]
    extra = []
    for i, (a, b) in enumerate(shots):
        if b - a > LONG_SHOT:
            n = int((b - a) // LONG_SHOT)
            extra += [(i, round(a + (k + 0.5) * (b - a) / (n + 1), 3)) for k in range(n + 1)]
            mids = [m for m in mids if m[0] != i]
    picks = mids[:cap]
    room = cap - len(picks)
    if room > 0 and extra:
        step = max(1, len(extra) // room)
        picks += extra[::step][:room]
    return sorted(picks, key=lambda p: p[1])


def extract_frame(mp4: str | Path, t: float, out: Path, width: int = FRAME_WIDTH) -> bool:
    exe = shutil.which("ffmpeg")
    if not exe:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    res = subprocess.run([exe, "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(mp4), "-frames:v", "1",
                          "-vf", f"scale={width}:-2", "-q:v", "4", str(out)], capture_output=True, text=True)
    return res.returncode == 0 and out.is_file()


# Layer 3: local signals

def brightness(frame: Path) -> float | None:
    """Mean luma 0..1 of a frame (a black or blown-out shot is no good to show)."""
    exe = shutil.which("ffmpeg")
    if not exe:
        return None
    res = subprocess.run([exe, "-hide_banner", "-i", str(frame), "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                          "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"YAVG=([\d.]+)", res.stderr)
    return round(float(m.group(1)) / 255, 3) if m else None


def read_text(frame: Path) -> list[str]:
    """Words on screen via the Tesseract CLI, when installed; [] otherwise."""
    exe = shutil.which("tesseract")
    if not exe:
        return []
    res = subprocess.run([exe, str(frame), "-", "--psm", "11"], capture_output=True, text=True, timeout=60)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in res.stdout.splitlines()]
    return [ln for ln in lines if len(re.sub(r"[^A-Za-z0-9]", "", ln)) >= 3][:20]


def local_type(texts: list[str]) -> tuple[str, float]:
    """A guess from local signals alone: lots of readable text means a screen or slide."""
    words = sum(len(t.split()) for t in texts)
    return ("screen", 0.5) if words >= 12 else ("unknown", 0.0)


def build_index(mp4: str | Path, source: Source, reframe: Reframe | None, job_dir: str | Path,
                provider: str = "none", cap: int = MAX_FRAMES) -> VisualIndex:
    """Build and save the visual index of a normalized video. `provider`: "none", "ollama" or "claude"."""
    from hypercut.vision import providers

    job_dir = Path(job_dir)
    cuts = list(reframe.shots) if reframe and reframe.shots else scene_cuts(mp4)
    spans = shots_from_cuts(cuts, source.duration)
    shots = [Shot(id=f"shot_{i + 1:03d}", start=round(a, 3), end=round(b, 3)) for i, (a, b) in enumerate(spans)]
    frames: list[tuple[Shot, Observation, Path]] = []
    for i, t in sample_times(spans, cap):
        out = job_dir / FRAMES_DIR / f"f{t:08.3f}.jpg"
        if not extract_frame(mp4, t, out):
            continue
        texts = read_text(out)
        kind, conf = local_type(texts)
        obs = Observation(t=t, frame=out.name, visible_text=texts, brightness=brightness(out), scene_type=kind, confidence=conf)
        shots[i].observations.append(obs)
        frames.append((shots[i], obs, out))
    described = providers.get(provider).describe([f for _, _, f in frames], [o.t for _, o, _ in frames])
    for (_, obs, _), d in zip(frames, described):
        if d:
            providers.merge(obs, d)
    index = VisualIndex(duration=source.duration, provider=provider, shots=shots)
    save(index, job_dir / INDEX_FILE)
    return index


def summary(index: VisualIndex, limit: int = 60) -> str:
    """The index as a few lines for a prompt: one per shot, with what it shows."""
    lines = []
    for s in index.shots[:limit]:
        bits = [s.scene_type]
        desc = next((o.description for o in s.observations if o.description), "")
        if desc:
            bits.append(desc[:100])
        text = [t for o in s.observations for t in o.visible_text][:4]
        if text:
            bits.append("text: " + " | ".join(t[:40] for t in text))
        objs = sorted({x for o in s.observations for x in o.objects})[:6]
        if objs:
            bits.append("objects: " + ", ".join(objs))
        lines.append(f"{s.start:.1f}-{s.end:.1f}: " + "; ".join(bits))
    return "\n".join(lines)


def screen_words(index: VisualIndex) -> list[str]:
    """Distinct words written on screen anywhere in the footage (brand and product names, mostly)."""
    words: dict[str, str] = {}
    for s in index.shots:
        for o in s.observations:
            for line in o.visible_text:
                for w in re.findall(r"[A-Za-z][A-Za-z0-9'’-]{3,}", line):
                    words.setdefault(w.lower(), w)
    return list(words.values())


def fix_words(transcript, index: VisualIndex, threshold: float = 0.8) -> list[Correction]:
    """Respell transcript words the way the footage writes them, for names speech recognition gets wrong
    ("Kachaba" spoken, KACHAVA on the bottle). Only close, longer words, and never common words that are simply
    different. Changes `transcript` in place and returns what changed."""
    from difflib import SequenceMatcher

    written = screen_words(index)
    if not written:
        return []
    strip = lambda text: re.sub(r"^[^\w]+|[^\w]+$", "", text)  # noqa: E731
    # Speech recognition capitalizes what it takes for a name; ordinary words ("shape" vs "SHAKE") are left alone.
    ws = transcript.words
    names = {strip(w.text).lower() for i, w in enumerate(ws)
             if strip(w.text)[:1].isupper() and i > 0 and not re.search(r"[.!?…]\W*$", ws[i - 1].text)}
    out = []
    for w in transcript.words:
        core = strip(w.text)
        if len(core) < 5 or core.lower() not in names:
            continue
        best, score = None, 0.0
        for cand in written:
            if cand.lower() == core.lower():
                best = None
                break
            r = SequenceMatcher(None, core.lower(), cand.lower()).ratio()
            if r > score:
                best, score = cand, r
        if best and score >= threshold and abs(len(best) - len(core)) <= 2:
            fixed = best if not best.isupper() else best.capitalize()
            if core[:1].islower():
                fixed = fixed.lower()
            out.append(Correction(t=w.start, heard=core, written=fixed))
            w.text = w.text.replace(core, fixed, 1)
    return out


def showing_spans(index: VisualIndex) -> list[tuple[float, float, Shot]]:
    """Source spans of shots that show something themselves (a screen, a product, other footage)."""
    return [(s.start, s.end, s) for s in index.shots if s.scene_type in SHOWING]


def keep_footage(plan, index: VisualIndex) -> list[str]:
    """Visual relevance: where a shot already shows what is being talked about, play the footage instead of
    covering it with a drawn visual. Full-frame visuals mostly over such a shot are dropped, and split or
    visual layout over it goes back to the footage. Returns what was changed, in words."""
    from hypercut import edit

    changes = []
    for a, b, shot in showing_spans(index):
        for g in list(plan.graphics):
            if g.type not in edit.VISUAL_TYPES or g.type == "media":
                continue
            over = min(g.end, b) - max(g.start, a)
            if over > 0.5 * (g.end - g.start):
                plan.graphics.remove(g)
                what = next((o.description for o in shot.observations if o.description), shot.scene_type)
                changes.append(f"Kept the footage at {a:.1f}-{b:.1f} s instead of {g.id}: it shows {what}")
        if any(s.mode != "speaker" and min(s.end, b) - max(s.start, a) > 0.3 for s in plan.layout):
            edit.set_layout(plan, a, b, "speaker")
    return changes
