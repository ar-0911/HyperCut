import xml.etree.ElementTree as ET
import zipfile

from hypercut import export
from hypercut.plan import EditPlan, Reframe, ReframeKey, Segment, Source, Transcript, Word

SOURCE = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=20)


def _plan():
    return EditPlan(
        source=SOURCE,
        segments=[Segment(start=2, end=4, reason="hook"), Segment(start=0, end=10, reason="body")],
        transcript=Transcript(words=[Word(text="Hello", start=2.0, end=2.5), Word(text="there.", start=2.6, end=3.0)]),
        reframe=Reframe(keys=[ReframeKey(t=0, cx=0.3, cy=0.4), ReframeKey(t=5, cx=0.3, cy=0.4)]),
    )


def test_clips_are_back_to_back_frames():
    cs = export.clips(_plan())
    assert [(c.src_in, c.frames, c.seq_in) for c in cs] == [(60, 60, 0), (0, 300, 60)]


def test_framing_fills_the_height_and_follows_the_speaker_within_the_edges():
    scale, shift = export._framing(_plan(), 0.3)
    assert scale == 1920 / 1080
    assert shift > 0 and shift <= (1920 * scale - 1080) / 2


def test_timelines_are_valid_xml_with_footage_and_overlays(tmp_path):
    (tmp_path / "normalized.mp4").write_bytes(b"v")
    overlays = tmp_path / "overlays.mov"
    overlays.write_bytes(b"o")
    archive = export.export(tmp_path, _plan(), overlays=overlays)
    fcp = ET.parse(tmp_path / "export" / "timeline.fcpxml").getroot()
    spine = fcp.find(".//spine")
    clips = spine.findall("asset-clip")
    assert len(clips) == 2 and clips[0].get("start") == "2s" and clips[1].get("offset") == "2s"
    assert clips[0].find("asset-clip").get("lane") == "1"
    xm = ET.parse(tmp_path / "export" / "timeline.xml").getroot()
    tracks = xm.findall(".//video/track")
    assert len(tracks) == 2 and [c.findtext("in") for c in tracks[0].findall("clipitem")] == ["60", "0"]
    names = zipfile.ZipFile(archive).namelist()
    assert {"hypercut-export/timeline.fcpxml", "hypercut-export/timeline.xml", "hypercut-export/captions.srt",
            "hypercut-export/footage.mp4", "hypercut-export/overlays.mov", "hypercut-export/README.txt"} <= set(names)


def test_captions_play_twice_in_a_cold_open():
    srt = export.reel_srt(_plan())
    assert srt.count("Hello there.") == 2 and "00:00:00,000 --> 00:00:01,000" in srt
