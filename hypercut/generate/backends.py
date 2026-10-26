"""Where generated pictures and clips come from (ADR 0016).

    fal    hosted models through fal.ai's queue API (FAL_KEY): an image model for stills, an image-to-video model
           that animates a still. One key covers many models; pick them with HYPERCUT_GEN_IMAGE_MODEL /
           HYPERCUT_GEN_VIDEO_MODEL.
    local  open models on this machine through `diffusers` (HYPERCUT_GEN_LOCAL=1; needs a CUDA GPU with 16-24 GB):
           Z-Image-Turbo for stills, Wan 2.2 TI2V 5B for clips, both Apache 2.0. Nothing leaves the machine.

Only the prompt (written from the transcript) is sent anywhere: never the speaker's footage. Real stock footage
comes from `hypercut.generate.stock`.
"""

from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

PORTRAIT = (1080, 1920)

FAL_IMAGE_MODEL = "fal-ai/flux-2-pro"
FAL_VIDEO_MODEL = "fal-ai/kling-video/v2.1/standard/image-to-video"
LOCAL_IMAGE_MODEL = "Tongyi-MAI/Z-Image-Turbo"
LOCAL_VIDEO_MODEL = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"

# Rough US$ per still and per second of clip, for the budget. Prices move; these err high.
IMAGE_COST = {FAL_IMAGE_MODEL: 0.05}
VIDEO_COST_PER_SECOND = {FAL_VIDEO_MODEL: 0.06}
DEFAULT_IMAGE_COST = 0.08
DEFAULT_VIDEO_COST_PER_SECOND = 0.15
CLIP_SECONDS = 5  # image-to-video models make 5 s clips; the reel plays as much as it needs

FAL_QUEUE = "https://queue.fal.run"
POLL_SECONDS = 2.0
TIMEOUT_SECONDS = 600.0


class GenerateError(RuntimeError):
    pass


@dataclass
class Made:
    """One file a backend made, saved at `path`."""

    path: Path
    kind: str  # "image" | "video"
    model: str
    cost: float
    duration: float | None = None
    extra: dict = field(default_factory=dict)


class Backend:
    name = ""

    def image(self, prompt: str, out: Path, seed: int | None = None) -> Made:
        raise NotImplementedError

    def video(self, prompt: str, still: Path, out: Path, seed: int | None = None) -> Made:
        raise NotImplementedError

    def image_cost(self) -> float:
        return DEFAULT_IMAGE_COST

    def video_cost(self) -> float:
        return DEFAULT_VIDEO_COST_PER_SECOND * CLIP_SECONDS


# --- HTTP (module level so tests can swap them) ----------------------------------------------------


def http_json(method: str, url: str, headers: dict | None = None, body: dict | None = None, params: dict | None = None) -> dict:
    import httpx

    res = httpx.request(method, url, headers=headers, json=body, params=params, timeout=120, follow_redirects=True)
    if res.status_code >= 400:
        raise GenerateError(f"{method} {url.split('?')[0]} failed: {res.status_code} {res.text[:300]}")
    return res.json()


def download(url: str, out: Path, headers: dict | None = None) -> Path:
    import httpx

    with httpx.stream("GET", url, headers=headers, timeout=300, follow_redirects=True) as res:
        if res.status_code >= 400:
            raise GenerateError(f"download failed: {res.status_code}")
        with out.open("wb") as f:
            for chunk in res.iter_bytes():
                f.write(chunk)
    return out


def data_uri(path: Path) -> str:
    mime = {".png": "image/png", ".webp": "image/webp"}.get(path.suffix.lower(), "image/jpeg")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


# --- fal.ai ---------------------------------------------------------------------------------------


class FalBackend(Backend):
    name = "fal"

    def __init__(self, key: str, image_model: str | None = None, video_model: str | None = None):
        self.key = key
        self.image_model = image_model or os.environ.get("HYPERCUT_GEN_IMAGE_MODEL") or FAL_IMAGE_MODEL
        self.video_model = video_model or os.environ.get("HYPERCUT_GEN_VIDEO_MODEL") or FAL_VIDEO_MODEL

    def image_cost(self) -> float:
        return IMAGE_COST.get(self.image_model, DEFAULT_IMAGE_COST)

    def video_cost(self) -> float:
        return VIDEO_COST_PER_SECOND.get(self.video_model, DEFAULT_VIDEO_COST_PER_SECOND) * CLIP_SECONDS

    def _run(self, model: str, body: dict) -> dict:
        """Submit to fal's queue and wait for the result."""
        headers = {"Authorization": f"Key {self.key}"}
        job = http_json("POST", f"{FAL_QUEUE}/{model}", headers, body)
        status_url, response_url = job.get("status_url"), job.get("response_url")
        if not status_url or not response_url:
            raise GenerateError(f"fal did not queue the request: {str(job)[:300]}")
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while True:
            state = http_json("GET", status_url, headers)
            if state.get("status") == "COMPLETED":
                break
            if state.get("status") not in ("IN_QUEUE", "IN_PROGRESS"):
                raise GenerateError(f"fal request failed: {str(state)[:300]}")
            if time.monotonic() > deadline:
                raise GenerateError("fal request timed out")
            time.sleep(POLL_SECONDS)
        return http_json("GET", response_url, headers)

    def image(self, prompt: str, out: Path, seed: int | None = None) -> Made:
        body: dict = {"prompt": prompt, "image_size": {"width": PORTRAIT[0], "height": PORTRAIT[1]}, "num_images": 1,
                      "output_format": "jpeg", "enable_safety_checker": True}
        if seed is not None:
            body["seed"] = seed
        result = self._run(self.image_model, body)
        images = result.get("images") or ([result["image"]] if isinstance(result.get("image"), dict) else [])
        if not images or not images[0].get("url"):
            raise GenerateError("fal returned no image")
        download(images[0]["url"], out)
        return Made(out, "image", self.image_model, self.image_cost())

    def video(self, prompt: str, still: Path, out: Path, seed: int | None = None) -> Made:
        body: dict = {"prompt": prompt, "image_url": data_uri(still), "duration": str(CLIP_SECONDS),
                      "negative_prompt": "text, captions, watermark, logo, people, faces, blur, distortion"}
        if seed is not None:
            body["seed"] = seed
        result = self._run(self.video_model, body)
        video = result.get("video") or {}
        if not video.get("url"):
            raise GenerateError("fal returned no video")
        download(video["url"], out)
        return Made(out, "video", self.video_model, self.video_cost(), duration=float(CLIP_SECONDS))


# --- local (diffusers) ---------------------------------------------------------------------------


class LocalBackend(Backend):
    """Open models on this machine. Loaded on first use and kept; one generation at a time."""

    name = "local"

    def __init__(self, image_model: str | None = None, video_model: str | None = None):
        self.image_model = image_model or os.environ.get("HYPERCUT_GEN_LOCAL_IMAGE_MODEL") or LOCAL_IMAGE_MODEL
        self.video_model = video_model or os.environ.get("HYPERCUT_GEN_LOCAL_VIDEO_MODEL") or LOCAL_VIDEO_MODEL
        self._pipes: dict[str, object] = {}

    def image_cost(self) -> float:
        return 0.0

    def video_cost(self) -> float:
        return 0.0

    def _pipe(self, model: str):
        if model not in self._pipes:
            try:
                import torch
                from diffusers import DiffusionPipeline
            except ImportError as e:
                raise GenerateError("local generation needs `pip install hypercut[local-gen]` (torch, diffusers)") from e
            if not torch.cuda.is_available():
                raise GenerateError("local generation needs a CUDA GPU")
            pipe = DiffusionPipeline.from_pretrained(model, torch_dtype=torch.bfloat16)
            pipe.enable_model_cpu_offload()  # fits 16-24 GB cards
            self._pipes[model] = pipe
        return self._pipes[model]

    def image(self, prompt: str, out: Path, seed: int | None = None) -> Made:
        import torch

        pipe = self._pipe(self.image_model)
        gen = torch.Generator("cuda").manual_seed(seed) if seed is not None else None
        # Turbo models want few steps and no guidance; 576x1024 keeps the 9:16 frame within memory.
        image = pipe(prompt=prompt, width=576, height=1024, num_inference_steps=9, guidance_scale=0.0, generator=gen).images[0]
        image.save(out, quality=92)
        return Made(out, "image", self.image_model, 0.0)

    def video(self, prompt: str, still: Path, out: Path, seed: int | None = None) -> Made:
        import inspect

        import torch
        from diffusers.utils import export_to_video, load_image

        pipe = self._pipe(self.video_model)
        fps = 24
        kwargs: dict = {"prompt": prompt, "width": 704, "height": 1280, "num_frames": fps * CLIP_SECONDS + 1,
                        "num_inference_steps": 40, "guidance_scale": 5.0}
        if "image" in inspect.signature(pipe.__call__).parameters:
            kwargs["image"] = load_image(str(still)).resize((704, 1280))
        if seed is not None:
            kwargs["generator"] = torch.Generator("cuda").manual_seed(seed)
        frames = pipe(**kwargs).frames[0]
        export_to_video(frames, str(out), fps=fps)
        return Made(out, "video", self.video_model, 0.0, duration=float(CLIP_SECONDS))


def configured() -> Backend | None:
    """The generation backend this machine is set up for, or None (generation off)."""
    if os.environ.get("HYPERCUT_GEN_LOCAL", "").lower() in ("1", "true", "yes"):
        return LocalBackend()
    if key := os.environ.get("FAL_KEY"):
        return FalBackend(key)
    return None


def video_enabled() -> bool:
    """Clips for the full-screen motion moments: on with a backend unless HYPERCUT_GEN_VIDEO=0."""
    return configured() is not None and os.environ.get("HYPERCUT_GEN_VIDEO", "1").lower() not in ("0", "false", "no")
