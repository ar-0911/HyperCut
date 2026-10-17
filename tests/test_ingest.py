import subprocess
import wave

import pytest

from hypercut.ingest import IngestError, ingest
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


def test_rejects_missing_audio(tmp_path):
    clip = make_clip(tmp_path / "silent.mp4", 11, audio=False)
    with pytest.raises(IngestError, match="no audio"):
        ingest(clip, tmp_path / "job")


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
