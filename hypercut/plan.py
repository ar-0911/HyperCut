"""The edit plan: the one contract every pipeline stage reads or writes.

Every time value is in seconds on the SOURCE video's timeline. The renderer maps
source time to output time through `segments`, so analyzers never need to know
what has been cut.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Span(_Model):
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> "Span":
        if self.end <= self.start:
            raise ValueError(f"end ({self.end}) must be after start ({self.start})")
        return self


class Source(_Model):
    path: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)
    duration: float = Field(gt=0)


class Output(_Model):
    width: int = 1080
    height: int = 1920
    fps: float = 30


class Word(Span):
    text: str
    speaker: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class Transcript(_Model):
    language: str = "en"
    words: list[Word] = []


class Segment(Span):
    """A piece of source video kept in the output. Played in list order."""

    reason: Literal["hook", "body"] = "body"


class HookCandidate(Span):
    text: str
    score: float = Field(ge=0, le=1)
    why: str = ""


class Hook(_Model):
    strategy: Literal["cold_open", "trim"] = "cold_open"
    chosen: int = 0  # index into candidates
    candidates: list[HookCandidate] = []


GraphicType = Literal[
    "kinetic_text",
    "stat_card",
    "emoji_burst",
    "list_build",
    "lower_third",
    "progress_bar",
    # Visuals: shown in the top panel of a "split" span, full frame in a "visual" span, as a card off
    # the face otherwise.
    "illustration",  # props: {"viewBox", "defs", "layers": [svg fragments, revealed in order], "title", "brief"}
    # Footage or a picture the user imported in the editor (B-roll). Never produced by analyze.
    # props: {"src": file name in the job folder, "kind": "image" | "video", "fit": "cover" | "contain",
    #         "trim_start": seconds into the clip, "duration": clip length in seconds, "label"}
    "media",
]

# Graphic types the analyze stage may propose; "media" only comes from the user's own uploads.
GENERATED_GRAPHIC_TYPES: tuple[str, ...] = tuple(t for t in get_args(GraphicType) if t != "media")


class Graphic(Span):
    id: str
    type: GraphicType
    # Free-form per template, e.g. {"text": "10x"} or {"items": ["a", "b"]}.
    props: dict = {}
    # Where it sits, normalized 0..1 on the output frame. The renderer keeps
    # graphics off the face using `reframe` when this is omitted.
    anchor: Literal["auto", "top", "center", "bottom"] = "auto"


class LayoutSpan(Span):
    """How the frame is arranged for a stretch of the source. Outside every span: "speaker"."""

    # speaker: speaker fills the frame. split: speaker in the bottom half, visuals above.
    # visual: the visual fills the frame while the speaker keeps talking (B-roll).
    mode: Literal["speaker", "split", "visual"] = "speaker"


class Zoom(Span):
    scale: float = Field(default=1.15, ge=1, le=2)
    ease: Literal["linear", "ease_in_out", "snap"] = "ease_in_out"


class ReframeKey(_Model):
    t: float = Field(ge=0)
    # Normalized 0..1 on the source frame. cx: horizontal crop center. cy: the face's height in the
    # frame (the crop is full height); older plans have 0.5 here.
    cx: float = Field(ge=0, le=1)
    cy: float = Field(ge=0, le=1)


class Reframe(_Model):
    keys: list[ReframeKey] = []  # empty: center crop


class CaptionStyle(_Model):
    font: str = "Montserrat"
    weight: int = 800
    size: int = 72  # px on the 1080x1920 output
    color: str = "#FFFFFF"
    highlight_color: str = "#FFE600"
    stroke_color: str = "#000000"
    stroke_width: int = 6
    uppercase: bool = True
    position: Literal["top", "middle", "bottom"] = "bottom"
    words_per_line: int = Field(default=3, ge=1, le=8)
    animation: Literal["karaoke", "pop", "typewriter", "bounce"] = "pop"


class GraphicsStyle(_Model):
    density: Literal["minimal", "balanced", "heavy"] = "balanced"
    theme: Literal["clean", "bold", "playful", "cinematic"] = "bold"
    accent_color: str = "#FFE600"


class Pacing(_Model):
    remove_fillers: bool = True
    max_silence: float = Field(default=0.35, ge=0)  # longer gaps get cut


class Camera(_Model):
    zoom_frequency: Literal["none", "low", "medium", "high"] = "medium"
    zoom_scale: float = Field(default=1.15, ge=1, le=2)


class Style(_Model):
    name: str = "bold_creator"
    caption: CaptionStyle = CaptionStyle()
    graphics: GraphicsStyle = GraphicsStyle()
    pacing: Pacing = Pacing()
    camera: Camera = Camera()


class EditPlan(_Model):
    version: Literal[1] = SCHEMA_VERSION
    source: Source
    output: Output = Output()
    transcript: Transcript = Transcript()
    hook: Hook = Hook()
    segments: list[Segment] = []  # empty: whole source, unedited
    graphics: list[Graphic] = []
    zooms: list[Zoom] = []
    layout: list[LayoutSpan] = []  # empty: speaker full frame throughout
    reframe: Reframe = Reframe()
    style: Style = Style()

    @model_validator(mode="after")
    def _within_source(self) -> "EditPlan":
        limit = self.source.duration + 1e-6
        for name in ("segments", "graphics", "zooms", "layout"):
            for item in getattr(self, name):
                if item.end > limit:
                    raise ValueError(f"{name}: {item.end}s is past the source end ({self.source.duration}s)")
        if self.hook.candidates and not 0 <= self.hook.chosen < len(self.hook.candidates):
            raise ValueError("hook.chosen is not a valid candidate index")
        return self

    def output_duration(self) -> float:
        if not self.segments:
            return self.source.duration
        return sum(s.end - s.start for s in self.segments)


def load(path: str | Path) -> EditPlan:
    return EditPlan.model_validate_json(Path(path).read_text())


def save(plan: EditPlan, path: str | Path) -> None:
    Path(path).write_text(plan.model_dump_json(indent=2) + "\n")


def json_schema() -> dict:
    return EditPlan.model_json_schema()


if __name__ == "__main__":
    # Regenerate the checked-in schema for the TypeScript side.
    out = Path(__file__).resolve().parent.parent / "schema" / "edit_plan.schema.json"
    out.write_text(json.dumps(json_schema(), indent=2) + "\n")
    print(f"wrote {out}")
