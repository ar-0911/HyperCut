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
    # Effects AROUND the cut-out speaker (green-screen effects, ADR 0610): drawn partly behind and partly
    # in front of the speaker, never over the face. Only with `style.depth.enabled`; `layer` is ignored.
    # orbit / fly_out props: {"items": [objects, 1-3 words], "art": {item: {"viewBox", "body"}}}, art being
    # Claude-drawn sticker SVG per item (missing: the renderer uses a built-in icon or the word)
    "orbit",  # drawn graphics circling the speaker's shoulders
    "fly_out",  # drawn graphics bursting from behind the head toward the camera
    "particles",  # props: {"kind": "sparkles" | "bokeh" | "confetti" | "embers", "color"}: depth-layered
    # Stage graphics (ADR 0611): what is said, drawn behind the cut-out speaker, only where it calls for one.
    # card_stack props: {"cards": [{"title": 1-3 words, "brief": what to draw, "viewBox", "defs", "layers"}]}:
    #   1-3 illustrated cards sliding out from behind the speaker into the free side of the frame.
    "card_stack",
    # scene props: {"title", "brief", "viewBox", "defs", "layers"}: a drawn world replacing the room; the
    #   speaker is pulled back a little so it shows.
    "scene",
    # chart props: {"headline", "kind": "line" | "bars", "values": [numbers], "labels": [str], "unit"}: an
    #   animated chart panel behind the pulled-back speaker, for numbers that are actually said.
    "chart",
    # Motion graphic (ADR 0612): the reel cuts away from the speaker to a full-screen 3D scene of what is
    # said for 2-3 s (the speaker keeps talking). props: {"title": 1-4 words, "idea": what to show,
    # "scene": {"objects": [...], "camera": {...}}}: the scene Claude designed (hypercut.analyze.motion).
    "motion",
]

# Effects around the cut-out speaker; analyze only proposes them when green-screen effects are on.
AROUND_GRAPHIC_TYPES: tuple[str, ...] = ("orbit", "fly_out", "particles")
# Stage graphics behind the cut-out speaker (ADR 0611); also only with green-screen effects on.
STAGE_GRAPHIC_TYPES: tuple[str, ...] = ("card_stack", "scene", "chart")
# Graphic types the analyze stage's main list offers; "media" only comes from the user's own uploads,
# motion graphics have their own list, and emoji are never proposed (Adi, 2026-10-18).
GENERATED_GRAPHIC_TYPES: tuple[str, ...] = tuple(
    t for t in get_args(GraphicType)
    if t not in ("media", "motion", "emoji_burst") and t not in AROUND_GRAPHIC_TYPES + STAGE_GRAPHIC_TYPES
)


class Graphic(Span):
    id: str
    type: GraphicType
    # Free-form per template, e.g. {"text": "10x"} or {"items": ["a", "b"]}.
    props: dict = {}
    # Where it sits, normalized 0..1 on the output frame. The renderer keeps
    # graphics off the face using `reframe` when this is omitted.
    anchor: Literal["auto", "top", "center", "bottom"] = "auto"
    # front: over the speaker (the default). behind: between the background and the cut-out speaker, so
    # the speaker's head and body pass in front of it (needs `style.depth.cutout`; ADR 0901, 0614). Big text
    # behind the speaker is drawn as a title around the head; any other type fills the frame behind them.
    layer: Literal["front", "behind"] = "front"


class LayoutSpan(Span):
    """How the frame is arranged for a stretch of the source. Outside every span: "speaker"."""

    # speaker: speaker fills the frame. split: speaker in the bottom half, visuals above.
    # visual: the visual fills the frame while the speaker keeps talking (B-roll).
    mode: Literal["speaker", "split", "visual"] = "speaker"


BackgroundKind = Literal["original", "blur", "dim", "color", "gradient", "media"]


class BackgroundSpan(Span):
    """What is behind the cut-out speaker for a stretch of the source (needs `style.depth.cutout`).

    original: the real background. blur: the real background out of focus. dim: darkened, a spotlight on
    the speaker. color / gradient: the studio set (a grid floor and wall, never a flat colour, ADR 0613), its
    light washed with `color` (default: untinted).
    media: an imported picture or clip (`src`, a file in the job folder). Outside every span the style's
    `depth.background` applies.
    """

    kind: BackgroundKind = "blur"
    color: str | None = None
    src: str | None = None
    # 0..1: how far a replaced background drifts and scales against the speaker, for a 3D feel.
    parallax: float = Field(default=0.0, ge=0, le=1)


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
    # Source times where a new shot starts (hard cuts in the source), for animated transitions (ADR 0613).
    shots: list[float] = []
    # Source times where, within one shot of two or more people, the crop moves to the person who started
    # talking (ADR 0506). The keys already jump there; this says why.
    switches: list[float] = []


# Caption fonts the renderer bundles (Google Fonts). Any other name falls back to a system sans-serif.
CAPTION_FONTS = (
    "Montserrat", "Inter", "Poppins", "Bebas Neue", "Anton", "Oswald", "Archivo Black",
    "Playfair Display", "Instrument Serif", "Archivo Expanded", "Permanent Marker", "Bangers",
)


class CaptionStyle(_Model):
    font: str = Field(default="Montserrat", description="One of: " + ", ".join(CAPTION_FONTS))
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
    # A rounded box behind each caption line (a CSS colour, e.g. "#000000B3"), instead of an outline.
    box: str | None = None


class GraphicsStyle(_Model):
    density: Literal["minimal", "balanced", "heavy"] = "balanced"
    theme: Literal["clean", "bold", "playful", "cinematic"] = "bold"
    accent_color: str = "#FFE600"
    # Stage graphics (ADR 0611): a second colour for tags and chart details (default: the accent) and the
    # dark colour of panels and card labels.
    secondary_color: str | None = None
    panel_color: str = "#0E1330"


class Pacing(_Model):
    remove_fillers: bool = True
    max_silence: float = Field(default=0.35, ge=0)  # longer gaps get cut
    # Pause kept on each side of a cut, so speech doesn't run into itself. Older plans used 0.08.
    keep_pause: float = Field(default=0.15, ge=0, le=1)
    # Playback speed of the whole reel (0.8 = 20% slower). Audio keeps its pitch.
    speed: float = Field(default=1.0, ge=0.5, le=2)


class Transitions(_Model):
    """How one kept piece of footage meets the next, and how the reel starts and ends."""

    # hard: straight cuts. smooth: a short crossfade with the sound eased across it.
    # zoom: straight cuts that alternate a slight punch-in, so jump cuts look intentional.
    # editorial: how an editor cuts a talking head (ADR 0614): J-cuts (the next piece's sound leads its
    # picture by a few frames), alternating punch-ins across jump cuts of the same shot, and a short settle
    # where the shot changes.
    style: Literal["hard", "smooth", "zoom", "editorial"] = "editorial"
    length: float = Field(default=0.2, ge=0, le=1)  # seconds, for smooth
    fade_in: float = Field(default=0.0, ge=0, le=3)  # seconds from black at the start
    fade_out: float = Field(default=0.8, ge=0, le=3)  # seconds to black (and silence) at the end


CutKind = Literal["drop", "whip", "zoom", "push"]


class CutTransition(_Model):
    """An animated transition into the shot or piece that starts at source time `at` (ADR 0613).

    The last frame before it is held and animated away over the incoming footage: drop (it falls off the
    bottom of the frame), whip (a fast blurred pan sideways), zoom (it pushes through toward the viewer),
    push (it slides up as the new shot slides in). Used sparingly, at shot and topic changes.
    """

    at: float = Field(ge=0)
    kind: CutKind = "drop"
    length: float = Field(default=0.5, ge=0.2, le=1.2)  # seconds


class Camera(_Model):
    zoom_frequency: Literal["none", "low", "medium", "high"] = "medium"
    zoom_scale: float = Field(default=1.15, ge=1, le=2)


class Depth(_Model):
    """Effects around the speaker (ADR 0901), and, only when asked, the speaker cut out of the frame.

    Off unless the user asks for it in their style prompt or in the editor. The cut-out (`cutout`) is a
    second, narrower opt-in: a different background or things behind the speaker (ADR 0614).
    """

    enabled: bool = Field(
        default=False,
        description="True only if the user explicitly asks for a green-screen look: text or graphics behind "
        "the speaker, things happening around or in front of the speaker, a removed, replaced, blurred or "
        "dimmed background, or a 3D/depth effect.",
    )
    cutout: bool = Field(
        default=False,
        description="True only if the user specifically asks for a different background (removed, replaced, "
        "blurred or dimmed) or for text or graphics behind the speaker. Otherwise every effect is animated "
        "over the real footage and the speaker is never cut out (ADR 0614).",
    )
    # Background where no `backgrounds` span says otherwise. Anything but "original" needs `cutout`.
    background: BackgroundKind = "original"
    behind_titles: bool = True  # analyze puts a few big titles behind the speaker's head (with `cutout`)
    # analyze adds a few cards and charts of what is said (over the real footage unless `cutout`) and, with
    # `enabled`, effects around the speaker (orbit, fly_out, particles)
    around: bool = True

    @model_validator(mode="after")
    def _replaced_background_is_cut_out(self) -> "Depth":
        # Plans from before `cutout` existed: a background that was asked to change still changes.
        if self.background != "original":
            self.cutout = True
        return self


EditingMode = Literal["talking_head", "podcast", "product_demo", "vlog"]


class Style(_Model):
    name: str = "bold_creator"
    # How the reel is edited, as opposed to how it looks (ADR 0025): `hypercut.modes` sets pacing, camera,
    # graphics and cuts for the mode, and tells the planner what makes a hook and what to keep.
    mode: EditingMode = "talking_head"
    caption: CaptionStyle = CaptionStyle()
    graphics: GraphicsStyle = GraphicsStyle()
    pacing: Pacing = Pacing()
    camera: Camera = Camera()
    transitions: Transitions = Transitions()
    depth: Depth = Depth()


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
    backgrounds: list[BackgroundSpan] = []  # only used with style.depth.cutout
    reframe: Reframe = Reframe()
    style: Style = Style()
    cuts: list[CutTransition] = []  # animated transitions; elsewhere footage meets by `style.transitions`

    @model_validator(mode="after")
    def _within_source(self) -> "EditPlan":
        limit = self.source.duration + 1e-6
        for name in ("segments", "graphics", "zooms", "layout", "backgrounds"):
            for item in getattr(self, name):
                if item.end > limit:
                    raise ValueError(f"{name}: {item.end}s is past the source end ({self.source.duration}s)")
        if self.hook.candidates and not 0 <= self.hook.chosen < len(self.hook.candidates):
            raise ValueError("hook.chosen is not a valid candidate index")
        # Plans from before `style.depth.cutout`: stretches whose background was changed keep changing.
        if any(b.kind != "original" for b in self.backgrounds):
            self.style.depth.cutout = True
        return self

    def output_duration(self) -> float:
        kept = self.source.duration if not self.segments else sum(s.end - s.start for s in self.segments)
        return kept / self.style.pacing.speed


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
