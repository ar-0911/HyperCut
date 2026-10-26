import subprocess
import wave

import pytest

from hypercut.ingest import IngestError, ingest, manifest
from hypercut.ingest.__main__ import main


def make_clip(path, seconds, fps=25, audio=True, size="160x120"):
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size={size}:rate={fps}:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=44100:duration={seconds}"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac"] if audio else []) + [str(path)]
    subprocess.run(cmd, check=True)
    return path


def test_ingest_normalizes(tmp_path):
    clip = make_clip(tmp_path / "in.mp4", 11, fps=25)
    source, mp4, wav = ingest(clip, tmp_path / "job")
    assert mp4.exists() and wav.exists()
    assert (source.width, source.height) == (160, 120)
    assert source.fps == pytest.approx(30, abs=0.01)
    assert source.duration == pytest.approx(11, abs=0.2)
    with wave.open(str(wav)) as w:
        assert w.getframerate() == 16000
        assert w.getnchannels() == 1
        assert w.getnframes() / 16000 == pytest.approx(11, abs=0.2)


def test_rejects_too_short(tmp_path):
    clip = make_clip(tmp_path / "short.mp4", 3)
    with pytest.raises(IngestError, match="minimum"):
        ingest(clip, tmp_path / "job")


def test_rejects_too_long(tmp_path):
    # Tiny frame size and low rate keep the 181 s clip cheap to generate.
    clip = make_clip(tmp_path / "long.mp4", 181, fps=1, size="64x64")
    with pytest.raises(IngestError, match="maximum"):
        ingest(clip, tmp_path / "job")


def test_no_sound_gets_a_silent_track(tmp_path):
    clip = make_clip(tmp_path / "silent.mp4", 11, audio=False)
    source, mp4, wav = ingest(clip, tmp_path / "job")
    assert source.duration == pytest.approx(11, abs=0.2)
    with wave.open(str(wav)) as w:
        assert w.getnframes() / 16000 == pytest.approx(11, abs=0.2)
    facts = manifest.load(tmp_path / "job")
    assert facts["audio"]["present"] is False and "no sound" in facts["warnings"][0]


def test_manifest(tmp_path):
    clip = make_clip(tmp_path / "in.mp4", 11, fps=25, size="480x854")
    ingest(clip, tmp_path / "job")
    facts = manifest.load(tmp_path / "job")
    assert facts["original"]["name"] == "in.mp4" and len(facts["original"]["sha256"]) == 64
    assert facts["video"]["orientation"] == "portrait" and facts["video"]["fps"] == 25
    assert facts["video"]["variable_frame_rate"] is False and facts["audio"]["present"]
    assert facts["normalized"]["fps"] == pytest.approx(30, abs=0.01)
    assert facts["stages"]["ingest"]["status"] == "done"
    assert any("soft" in w for w in facts["warnings"])  # 480 wide
    manifest.mark(tmp_path / "job", "transcribe", "running")
    assert manifest.load(tmp_path / "job")["stages"]["transcribe"]["status"] == "running"


def test_manifest_reads_rotation_vfr_and_hdr(tmp_path):
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"x")
    info = {"format": {"format_name": "mov", "duration": "12", "bit_rate": "800"}, "streams": [
        {"codec_type": "video", "width": 1920, "height": 1080, "r_frame_rate": "30/1", "avg_frame_rate": "2400/100",
         "color_transfer": "arib-std-b67", "side_data_list": [{"rotation": -90}]},
        {"codec_type": "audio", "codec_name": "aac", "channels": 2, "sample_rate": "48000"},
        {"codec_type": "audio"}]}
    facts = manifest.describe(info, clip)
    v = facts["video"]
    assert v["rotation"] == 90 and (v["display_width"], v["display_height"]) == (1080, 1920)
    assert v["orientation"] == "portrait" and v["variable_frame_rate"] and v["hdr"]
    assert facts["audio"]["tracks"] == 2 and facts["original"]["bitrate"] == 800
    text = " ".join(facts["warnings"])
    assert "variable frame rate" in text and "rotated by 90" in text and "HDR" in text and "2 audio tracks" in text


def test_rejects_non_video(tmp_path):
    bad = tmp_path / "x.mp4"
    bad.write_text("not a video")
    with pytest.raises(IngestError, match="Could not read"):
        ingest(bad, tmp_path / "job")


def test_missing_file(tmp_path):
    with pytest.raises(IngestError, match="not found"):
        ingest(tmp_path / "nope.mp4", tmp_path / "job")


def test_cli(tmp_path, capsys):
    clip = make_clip(tmp_path / "in.mp4", 11)
    assert main([str(clip), str(tmp_path / "out")]) == 0
    assert '"width": 160' in capsys.readouterr().out
    assert main([str(tmp_path / "nope.mp4"), str(tmp_path / "out")]) == 1


def test_ingest_caps_4k_at_1920_tall(tmp_path):
    clip = make_clip(tmp_path / "in.mp4", 11, size="3840x2160")
    source, _, _ = ingest(clip, tmp_path / "job")
    assert (source.width, source.height) == (3414, 1920)


def test_preview_copy(tmp_path):
    from hypercut.ingest import PROXY_HEIGHT, make_proxy, probe

    small = make_clip(tmp_path / "small.mp4", 1, size="320x240")
    assert make_proxy(small) is None  # already light
    big = make_clip(tmp_path / "big.mp4", 1, size="1080x1920")
    out = make_proxy(big)
    info = probe(out)
    assert out.name == "proxy.mp4" and info["height"] == PROXY_HEIGHT and info["width"] == 540
