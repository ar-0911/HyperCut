"""Real footage and photos from stock libraries, credited (ADR 0016).

Providers, each on only when configured:
    pexels    PEXELS_API_KEY   clips and photos, free for commercial use, credit appreciated
    pixabay   PIXABAY_API_KEY  clips and photos, free for commercial use
    commons   HYPERCUT_STOCK=commons (no key): Wikimedia Commons photos, only public-domain, CC0 and CC BY
              (the credit is then shown on screen, which CC BY requires)

`find(query, brief, media)` searches, lets Claude look at the thumbnails and pick the shot that shows the brief
(or none), downloads it and returns it with its credit. Only the search words leave the machine.
"""

from __future__ import annotations

import html
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from hypercut import llm
from hypercut.generate.backends import GenerateError, download, http_json

log = logging.getLogger(__name__)

PER_PROVIDER = 6
MAX_CANDIDATES = 8
MAX_CLIP_SECONDS = 15.0
MAX_SIDE = 1920
OPEN_LICENSES = re.compile(r"^(cc0|public domain|pd|cc by( \d(\.\d)?)?)$", re.I)


@dataclass
class Candidate:
    provider: str
    kind: str  # "image" | "video"
    title: str
    thumb: str  # small picture URL, for choosing
    url: str  # file to download
    credit: str
    credit_url: str
    credit_required: bool = False
    width: int = 0
    height: int = 0
    duration: float | None = None


def providers() -> list[str]:
    names = []
    if os.environ.get("PEXELS_API_KEY"):
        names.append("pexels")
    if os.environ.get("PIXABAY_API_KEY"):
        names.append("pixabay")
    if "commons" in os.environ.get("HYPERCUT_STOCK", "").lower():
        names.append("commons")
    return names


def enabled() -> bool:
    return bool(providers())


# --- search --------------------------------------------------------------------------------------


def _best_file(files: list[dict]) -> dict | None:
    """The mp4 rendition closest to 1080 wide without going over 1920 on its longest side."""
    mp4 = [f for f in files if f.get("link") and (f.get("file_type") or "video/mp4") == "video/mp4"]
    fits = [f for f in mp4 if max(f.get("width") or 0, f.get("height") or 0) <= MAX_SIDE] or mp4
    return min(fits, key=lambda f: abs((f.get("width") or 0) - 1080), default=None)


def search_pexels(query: str, media: str) -> list[Candidate]:
    headers = {"Authorization": os.environ["PEXELS_API_KEY"]}
    out: list[Candidate] = []
    if media in ("video", "any"):
        data = http_json("GET", "https://api.pexels.com/videos/search", headers,
                         params={"query": query, "per_page": PER_PROVIDER, "orientation": "portrait"})
        for v in data.get("videos") or []:
            f = _best_file(v.get("video_files") or [])
            user = v.get("user") or {}
            if f and v.get("image"):
                out.append(Candidate("pexels", "video", _slug_title(v.get("url", "")), v["image"], f["link"],
                                     f"{user.get('name', 'Pexels')} / Pexels", v.get("url", ""),
                                     width=f.get("width") or 0, height=f.get("height") or 0, duration=v.get("duration")))
    if media in ("image", "any"):
        data = http_json("GET", "https://api.pexels.com/v1/search", headers,
                         params={"query": query, "per_page": PER_PROVIDER, "orientation": "portrait"})
        for p in data.get("photos") or []:
            src = p.get("src") or {}
            if src.get("medium") and (src.get("large2x") or src.get("original")):
                out.append(Candidate("pexels", "image", p.get("alt") or "", src["medium"], src.get("large2x") or src["original"],
                                     f"{p.get('photographer', 'Pexels')} / Pexels", p.get("url", ""),
                                     width=p.get("width") or 0, height=p.get("height") or 0))
    return out


def search_pixabay(query: str, media: str) -> list[Candidate]:
    key = os.environ["PIXABAY_API_KEY"]
    out: list[Candidate] = []
    if media in ("video", "any"):
        data = http_json("GET", "https://pixabay.com/api/videos/", params={"key": key, "q": query, "per_page": PER_PROVIDER, "safesearch": "true"})
        for h in data.get("hits") or []:
            videos = h.get("videos") or {}
            f = videos.get("large") if (videos.get("large") or {}).get("url") else videos.get("medium") or {}
            if f.get("url") and f.get("thumbnail"):
                out.append(Candidate("pixabay", "video", h.get("tags", ""), f["thumbnail"], f["url"],
                                     f"{h.get('user', 'Pixabay')} / Pixabay", h.get("pageURL", ""),
                                     width=f.get("width") or 0, height=f.get("height") or 0, duration=h.get("duration")))
    if media in ("image", "any"):
        data = http_json("GET", "https://pixabay.com/api/", params={"key": key, "q": query, "per_page": PER_PROVIDER,
                                                                    "image_type": "photo", "safesearch": "true"})
        for h in data.get("hits") or []:
            if h.get("webformatURL") and h.get("largeImageURL"):
                out.append(Candidate("pixabay", "image", h.get("tags", ""), h["webformatURL"], h["largeImageURL"],
                                     f"{h.get('user', 'Pixabay')} / Pixabay", h.get("pageURL", ""),
                                     width=h.get("imageWidth") or 0, height=h.get("imageHeight") or 0))
    return out


def _plain(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value or "")).split())


def search_commons(query: str, media: str) -> list[Candidate]:
    if media == "video":
        return []
    data = http_json("GET", "https://commons.wikimedia.org/w/api.php", {"User-Agent": "HyperCut/0.1 (local video editor)"}, params={
        "action": "query", "format": "json", "generator": "search", "gsrsearch": f"filetype:bitmap {query}",
        "gsrnamespace": 6, "gsrlimit": PER_PROVIDER * 2, "prop": "imageinfo", "iiprop": "url|extmetadata|size",
        "iiurlwidth": 1080,
    })
    out: list[Candidate] = []
    for page in (data.get("query") or {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        license_ = _plain((meta.get("LicenseShortName") or {}).get("value", ""))
        if not OPEN_LICENSES.match(license_) or not info.get("thumburl"):
            continue  # share-alike, non-commercial and unknown licences are skipped
        artist = _plain((meta.get("Artist") or {}).get("value", "")) or "Wikimedia Commons"
        needs_credit = license_.lower().startswith("cc by")
        title = re.sub(r"^File:|\.\w+$", "", page.get("title", ""))
        out.append(Candidate("commons", "image", title, info["thumburl"], info["thumburl"],
                             f"{artist[:60]}, {license_}, Wikimedia Commons", info.get("descriptionurl", ""),
                             credit_required=needs_credit, width=info.get("thumbwidth") or 0, height=info.get("thumbheight") or 0))
    return out[:PER_PROVIDER]


SEARCH = {"pexels": search_pexels, "pixabay": search_pixabay, "commons": search_commons}


def _slug_title(url: str) -> str:
    """Pexels names its pages after the shot: .../video/aerial-view-of-a-city-1234/."""
    m = re.search(r"/(?:video|photo)/([a-z0-9-]+?)-\d+/?$", url)
    return m.group(1).replace("-", " ") if m else ""


def search(query: str, media: str = "any") -> list[Candidate]:
    found: list[Candidate] = []
    for name in providers():
        try:
            found += SEARCH[name](query, media)
        except Exception as e:  # noqa: BLE001 - one provider down must not stop the others
            log.warning("stock search on %s failed: %s", name, e)
    # Clips first when both were asked for (B-roll moves), keeping each provider's ranking.
    if media == "any":
        found.sort(key=lambda c: c.kind != "video")
    return found[:MAX_CANDIDATES]


# --- choose --------------------------------------------------------------------------------------

PICK_PROMPT = """These are candidate stock shots for one moment of a vertical short video. The editor wants: {brief}
The speaker is saying: "{said}"

The shots, by number:
{listing}

Pick the shot that shows exactly that, looks professional and would read on a phone. Reject shots with visible \
text or watermarks, logos, or faces that would be mistaken for the speaker. If none fits, pick null.
Return {{"pick": <number or null>, "why": "<a few words>"}}"""


def choose(candidates: list[Candidate], brief: str, said: str = "", ask=None) -> Candidate | None:
    """Claude looks at the thumbnails and picks one, or none. Without a usable answer: the first one."""
    if not candidates:
        return None
    ask = ask or llm.ask_json
    with tempfile.TemporaryDirectory(prefix="hypercut-stock-") as tmp:
        thumbs = []
        for i, c in enumerate(candidates):
            try:
                thumbs.append(download(c.thumb, Path(tmp) / f"{i}.jpg"))
            except Exception:  # noqa: BLE001
                thumbs.append(None)
        shown = [(i, p) for i, p in enumerate(thumbs) if p is not None]
        if not shown:
            return candidates[0]
        listing = "\n".join(f"{n}: {candidates[i].kind}, \"{candidates[i].title[:80]}\"" for n, (i, _) in enumerate(shown))
        try:
            raw = ask(PICK_PROMPT.format(brief=brief[:600], said=said[:300], listing=listing), images=[p for _, p in shown])
        except Exception as e:  # noqa: BLE001
            log.warning("could not choose a stock shot, using the first: %s", e)
            return candidates[shown[0][0]]
    pick = raw.get("pick") if isinstance(raw, dict) else None
    if pick is None:
        return None
    if isinstance(pick, int) and 0 <= pick < len(shown):
        return candidates[shown[pick][0]]
    return candidates[shown[0][0]]


# --- fetch ---------------------------------------------------------------------------------------


def prepare_clip(src: Path, out: Path) -> float:
    """A silent H.264 mp4 of the first seconds, longest side at most 1920. Returns its length."""
    res = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-t", str(MAX_CLIP_SECONDS), "-an",
         "-vf", f"scale='min({MAX_SIDE},iw)':'min({MAX_SIDE},ih)':force_original_aspect_ratio=decrease"
                ":flags=bicubic,scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=30,format=yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-movflags", "+faststart", str(out)],
        capture_output=True, text=True,
    )
    if res.returncode != 0 or not out.is_file():
        raise GenerateError("could not convert the stock clip: " + res.stderr.strip()[-300:])
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                           capture_output=True, text=True)
    try:
        return float(probe.stdout.strip())
    except ValueError:
        return MAX_CLIP_SECONDS


def fetch(c: Candidate, out_stem: Path) -> tuple[Path, float | None]:
    """Download the chosen shot next to `out_stem` (a path without extension). Returns (file, clip length)."""
    if c.kind == "image":
        ext = ".png" if c.url.lower().split("?")[0].endswith(".png") else ".jpg"
        return download(c.url, out_stem.with_suffix(ext)), None
    raw = out_stem.with_suffix(".download")
    try:
        download(c.url, raw)
        out = out_stem.with_suffix(".mp4")
        return out, round(prepare_clip(raw, out), 3)
    finally:
        raw.unlink(missing_ok=True)
