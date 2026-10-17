"""The six named presets. Each is a complete, valid `Style`."""

from __future__ import annotations

from hypercut.plan import Camera, CaptionStyle, GraphicsStyle, Pacing, Style

DEFAULT_PRESET = "bold_creator"

PRESETS: dict[str, Style] = {
    "bold_creator": Style(
        name="bold_creator",
        caption=CaptionStyle(),
        graphics=GraphicsStyle(density="balanced", theme="bold", accent_color="#FFE600"),
        pacing=Pacing(remove_fillers=True, max_silence=0.35),
        camera=Camera(zoom_frequency="medium", zoom_scale=1.15),
    ),
    "clean_corporate": Style(
        name="clean_corporate",
        caption=CaptionStyle(
            font="Inter", weight=700, size=60, highlight_color="#4F8CFF", stroke_width=0,
            uppercase=False, position="bottom", words_per_line=4, animation="karaoke",
        ),
        graphics=GraphicsStyle(density="minimal", theme="clean", accent_color="#4F8CFF"),
        pacing=Pacing(remove_fillers=True, max_silence=0.5),
        camera=Camera(zoom_frequency="low", zoom_scale=1.08),
    ),
    "playful": Style(
        name="playful",
        caption=CaptionStyle(
            font="Poppins", weight=800, size=76, highlight_color="#FF4FA3", stroke_width=7,
            uppercase=False, position="middle", words_per_line=2, animation="bounce",
        ),
        graphics=GraphicsStyle(density="heavy", theme="playful", accent_color="#FF4FA3"),
        pacing=Pacing(remove_fillers=True, max_silence=0.3),
        camera=Camera(zoom_frequency="high", zoom_scale=1.2),
    ),
    "cinematic": Style(
        name="cinematic",
        caption=CaptionStyle(
            font="Playfair Display", weight=600, size=58, highlight_color="#F2C879",
            stroke_width=2, uppercase=False, position="bottom", words_per_line=5,
            animation="typewriter",
        ),
        graphics=GraphicsStyle(density="minimal", theme="cinematic", accent_color="#F2C879"),
        pacing=Pacing(remove_fillers=True, max_silence=0.7),
        camera=Camera(zoom_frequency="low", zoom_scale=1.1),
    ),
    "minimal": Style(
        name="minimal",
        caption=CaptionStyle(
            font="Inter", weight=600, size=52, highlight_color="#FFFFFF", stroke_width=0,
            uppercase=False, position="bottom", words_per_line=6, animation="pop",
        ),
        graphics=GraphicsStyle(density="minimal", theme="clean", accent_color="#FFFFFF"),
        pacing=Pacing(remove_fillers=False, max_silence=0.6),
        camera=Camera(zoom_frequency="none", zoom_scale=1.0),
    ),
    "podcast": Style(
        name="podcast",
        caption=CaptionStyle(
            font="Montserrat", weight=700, size=64, highlight_color="#3DDC97", stroke_width=4,
            uppercase=False, position="middle", words_per_line=4, animation="karaoke",
        ),
        graphics=GraphicsStyle(density="balanced", theme="clean", accent_color="#3DDC97"),
        pacing=Pacing(remove_fillers=True, max_silence=0.5),
        camera=Camera(zoom_frequency="medium", zoom_scale=1.1),
    ),
}

DESCRIPTIONS: dict[str, str] = {
    "bold_creator": "loud, high-energy creator look: big uppercase yellow captions, regular zooms",
    "clean_corporate": "professional and calm: smaller sentence-case captions, blue accent, few graphics",
    "playful": "fun and bouncy: pink accent, lots of graphics and emoji, frequent zooms",
    "cinematic": "moody and elegant: serif captions, gold accent, slow pacing, subtle camera",
    "minimal": "nearly invisible: small plain captions, no zooms, fillers kept, no frills",
    "podcast": "conversational: mid-screen green karaoke captions, moderate graphics and zooms",
}
