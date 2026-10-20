"""Hand the edit to a professional editor (ADR 0017): Final Cut Pro, DaVinci Resolve or Premiere Pro.

    export(job_dir) -> media/<job>/export/ and media/<job>/hypercut-export.zip

The folder holds:
    timeline.fcpxml   Final Cut Pro and DaVinci Resolve (FCPXML 1.10)
    timeline.xml      Premiere Pro and DaVinci Resolve (Final Cut Pro 7 XML, xmeml 5)
    captions.srt      the captions in reel time, for the editor's own caption track
    footage.mp4       the source video the cuts point at
    overlays.mov      graphics and captions alone on transparency (ProRes 4444), on the track above, when rendered
    README.txt        what carries over and what doesn't

Both timelines have the kept pieces of footage, in order, on track 1 (each scaled to fill the 9:16 frame and
centred on the speaker's average position in that piece), and the overlay clip on track 2. Zooms, punch-ins,
animated transitions and the reel's speed change are baked into nothing but the overlay; the footage cuts are
plain, so an editor can re-time them. Media paths are absolute file URLs to the export folder: if the folder
moves, the editor asks to relink.

CLI: python -m hypercut.export JOB_DIR [--overlays]
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from hypercut import edit
from hypercut import plan as plan_mod
from hypercut.plan import EditPlan, Transcript, Word
from hypercut.transcribe import to_srt

FOLDER = "export"
ZIP = "hypercut-export.zip"
OVERLAYS = "overlays.mov"
FOOTAGE = "footage.mp4"


@dataclass
class Clip:
    src_in: int  # frames into the footage
    frames: int
    seq_in: int  # frames into the timeline
    cx: float  # 0..1 crop centre on the source frame


def _rate(fps: float) -> tuple[Fraction, int, bool]:
    """Frame duration, whole timebase and NTSC flag for a frame rate (29.97 -> 1001/30000 s, 30, True)."""
    base = round(fps)
    ntsc = abs(fps - base) > 0.01
    return (Fraction(1001, base * 1000) if ntsc else Fraction(1, base)), base, ntsc


def _cx_at(plan: EditPlan, start: float, end: float) -> float:
    keys = [k.cx for k in plan.reframe.keys if start <= k.t <= end]
    if not keys:
        before = [k for k in plan.reframe.keys if k.t <= start]
        return before[-1].cx if before else 0.5
    return sum(keys) / len(keys)


def clips(plan: EditPlan) -> list[Clip]:
    """The kept pieces as whole frames on the footage's frame rate, back to back."""
    fps = plan.source.fps
    out, cursor = [], 0
    for s in plan.segments or [plan_mod.Segment(start=0, end=plan.source.duration)]:
        a, b = round(s.start * fps), round(s.end * fps)
        if b <= a:
            continue
        out.append(Clip(a, b - a, cursor, _cx_at(plan, s.start, s.end)))
        cursor += b - a
    return out


def _framing(plan: EditPlan, cx: float) -> tuple[float, float]:
    """Scale (1 = the source's own size) that fills the output height, and the horizontal shift in output pixels
    that puts the crop centre `cx` in the middle, kept so the frame never shows past the source's edge."""
    out_w, out_h = plan.output.width, plan.output.height
    scale = max(out_h / plan.source.height, out_w / plan.source.width)
    scaled_w = plan.source.width * scale
    shift = (0.5 - cx) * scaled_w
    limit = max(0.0, (scaled_w - out_w) / 2)
    return scale, max(-limit, min(limit, shift))


def reel_srt(plan: EditPlan) -> str:
    """The captions as played: every kept word at its reel time (a cold-open hook's words twice)."""
    speed = plan.style.pacing.speed
    words = []
    for w in plan.transcript.words:
        mid = (w.start + w.end) / 2
        for t in edit.to_reel(plan, mid):
            words.append(Word(text=w.text, start=round(t - (mid - w.start) / speed, 3), end=round(t + (w.end - mid) / speed, 3)))
    words.sort(key=lambda w: w.start)
    return to_srt(Transcript(words=words))


def _t(frames: int, frame: Fraction) -> str:
    v = frames * frame
    return f"{v.numerator}/{v.denominator}s" if v.denominator != 1 else f"{v.numerator}s"


def fcpxml(plan: EditPlan, footage: Path, overlays: Path | None, name: str) -> str:
    frame, _, ntsc = _rate(plan.source.fps)
    cs = clips(plan)
    total = sum(c.frames for c in cs)
    src_frames = round(plan.source.duration * plan.source.fps)
    fd = f"{frame.numerator}/{frame.denominator}s"
    out_w, out_h = plan.output.width, plan.output.height
    res = [
        f'<format id="r1" name="HyperCut {out_w}x{out_h}" frameDuration="{fd}" width="{out_w}" height="{out_h}"/>',
        f'<format id="r2" frameDuration="{fd}" width="{plan.source.width}" height="{plan.source.height}"/>',
        f'<asset id="r3" name="footage" start="0s" duration="{_t(src_frames, frame)}" hasVideo="1" hasAudio="1" format="r2" '
        f'audioSources="1" audioChannels="2"><media-rep kind="original-media" src={quoteattr(footage.resolve().as_uri())}/></asset>',
    ]
    if overlays:
        res.append(f'<asset id="r4" name="overlays" start="0s" duration="{_t(total, frame)}" hasVideo="1" format="r1">'
                   f'<media-rep kind="original-media" src={quoteattr(overlays.resolve().as_uri())}/></asset>')
    spine = []
    for i, c in enumerate(cs):
        scale, shift = _framing(plan, c.cx)
        # FCPXML positions are in percent of the frame height; conform "none" keeps the source's own pixel size.
        inner = [f'<adjust-conform type="none"/>',
                 f'<adjust-transform position="{shift / out_h * 100:.3f} 0" scale="{scale:.4f} {scale:.4f}"/>']
        if i == 0 and overlays:
            inner.append(f'<asset-clip ref="r4" lane="1" offset="{_t(c.src_in, frame)}" start="0s" duration="{_t(total, frame)}" name="overlays"/>')
        spine.append(f'<asset-clip ref="r3" name="footage {i + 1}" offset="{_t(c.seq_in, frame)}" start="{_t(c.src_in, frame)}" '
                     f'duration="{_t(c.frames, frame)}" format="r2" tcFormat="NDF">{"".join(inner)}</asset-clip>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="1.10">\n'
        f'<resources>\n{chr(10).join(res)}\n</resources>\n'
        f'<library><event name="HyperCut"><project name={quoteattr(name)}>'
        f'<sequence format="r1" duration="{_t(total, frame)}" tcStart="0s" tcFormat="{"DF" if ntsc else "NDF"}" audioLayout="stereo" audioRate="48k">'
        f'<spine>\n{chr(10).join(spine)}\n</spine></sequence></project></event></library>\n</fcpxml>\n'
    )


def _rate_xml(base: int, ntsc: bool) -> str:
    return f"<rate><timebase>{base}</timebase><ntsc>{'TRUE' if ntsc else 'FALSE'}</ntsc></rate>"


def xmeml(plan: EditPlan, footage: Path, overlays: Path | None, name: str) -> str:
    _, base, ntsc = _rate(plan.source.fps)
    rate = _rate_xml(base, ntsc)
    cs = clips(plan)
    total = sum(c.frames for c in cs)
    src_frames = round(plan.source.duration * plan.source.fps)
    out_w, out_h = plan.output.width, plan.output.height
    file_xml = (f'<file id="footage"><name>{FOOTAGE}</name><pathurl>{escape(footage.resolve().as_uri())}</pathurl>{rate}'
                f'<duration>{src_frames}</duration><media><video><samplecharacteristics><width>{plan.source.width}</width>'
                f'<height>{plan.source.height}</height></samplecharacteristics></video><audio><channelcount>2</channelcount></audio></media></file>')
    video, audio = [], []
    for i, c in enumerate(cs):
        scale, shift = _framing(plan, c.cx)
        common = (f"<name>footage {i + 1}</name><duration>{src_frames}</duration>{rate}<start>{c.seq_in}</start>"
                  f"<end>{c.seq_in + c.frames}</end><in>{c.src_in}</in><out>{c.src_in + c.frames}</out>")
        f = file_xml if i == 0 else '<file id="footage"/>'
        # Basic Motion: scale in percent; centre offset as a fraction of the sequence width / height.
        motion = ("<filter><effect><name>Basic Motion</name><effectid>basic</effectid><effectcategory>motion</effectcategory>"
                  "<effecttype>motion</effecttype><mediatype>video</mediatype>"
                  f"<parameter><parameterid>scale</parameterid><name>Scale</name><value>{scale * 100:.2f}</value></parameter>"
                  f"<parameter><parameterid>center</parameterid><name>Center</name><value><horiz>{shift / out_w:.4f}</horiz>"
                  "<vert>0</vert></value></parameter></effect></filter>")
        video.append(f'<clipitem id="v{i + 1}">{common}{f}{motion}</clipitem>')
        audio.append(f'<clipitem id="a{i + 1}">{common}<file id="footage"/><sourcetrack><mediatype>audio</mediatype>'
                     f'<trackindex>1</trackindex></sourcetrack></clipitem>')
    tracks = [f"<track>{''.join(video)}</track>"]
    if overlays:
        tracks.append(
            f'<track><clipitem id="overlays"><name>overlays</name><duration>{total}</duration>{rate}<start>0</start><end>{total}</end>'
            f'<in>0</in><out>{total}</out><file id="overlays-file"><name>{OVERLAYS}</name>'
            f'<pathurl>{escape(overlays.resolve().as_uri())}</pathurl>{rate}<duration>{total}</duration><media><video>'
            f'<samplecharacteristics><width>{out_w}</width><height>{out_h}</height></samplecharacteristics></video></media>'
            f'</file><alphatype>straight</alphatype></clipitem></track>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="5"><sequence id="hypercut">'
        f"<name>{escape(name)}</name><duration>{total}</duration>{rate}<media><video><format><samplecharacteristics>"
        f"{rate}<width>{out_w}</width><height>{out_h}</height><pixelaspectratio>square</pixelaspectratio>"
        f"</samplecharacteristics></format>{''.join(tracks)}</video><audio><track>{''.join(audio)}</track></audio>"
        "</media></sequence></xmeml>\n"
    )


README = """HyperCut export

timeline.fcpxml  Final Cut Pro (File > Import > XML) or DaVinci Resolve (File > Import > Timeline)
timeline.xml     Premiere Pro (File > Import) or DaVinci Resolve
captions.srt     the captions at reel time, to import as a caption track
footage.mp4      the source video the cuts point at
overlays.mov     graphics and captions on transparency (ProRes 4444), on the track above the footage{overlay_note}

Track 1 has every kept piece of footage in order, scaled to fill the 9:16 frame around the speaker.
Not carried over as edits: zooms and punch-ins, animated transitions, the speed change ({speed:.0%}), and
J-cuts. Check the framing of each clip after import. If you move this folder, relink the media when asked.
"""


def export(job_dir: str | Path, plan: EditPlan | None = None, overlays: Path | None = None) -> Path:
    """Write the export folder and zip in `job_dir`. `overlays`: an already rendered overlay clip to include."""
    job_dir = Path(job_dir)
    plan = plan or plan_mod.load(job_dir / "plan.json")
    out = job_dir / FOLDER
    out.mkdir(exist_ok=True)
    footage = out / FOOTAGE
    if not footage.exists():
        try:
            footage.hardlink_to(job_dir / "normalized.mp4")
        except OSError:
            shutil.copyfile(job_dir / "normalized.mp4", footage)
    ov = None
    if overlays is not None and overlays.is_file():
        ov = out / OVERLAYS
        if overlays.resolve() != ov.resolve():
            shutil.move(str(overlays), ov)
    name = f"HyperCut {job_dir.name}"
    (out / "timeline.fcpxml").write_text(fcpxml(plan, footage, ov, name))
    (out / "timeline.xml").write_text(xmeml(plan, footage, ov, name))
    (out / "captions.srt").write_text(reel_srt(plan))
    note = "" if ov else " (not rendered this time)"
    (out / "README.txt").write_text(README.format(overlay_note=note, speed=plan.style.pacing.speed))
    archive = job_dir / ZIP
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as z:  # video doesn't compress; store is fast
        for p in sorted(out.iterdir()):
            z.write(p, f"hypercut-export/{p.name}")
    return archive


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hypercut.export", description=__doc__.splitlines()[0])
    ap.add_argument("job_dir")
    ap.add_argument("--overlays", action="store_true", help="also render the graphics track (ProRes 4444; slow)")
    args = ap.parse_args(argv)
    job = Path(args.job_dir)
    overlays = None
    if args.overlays:
        from hypercut.run import render_plan

        overlays = render_plan(job, OVERLAYS, extra_args=["--overlays", "1"])
    print(f"wrote {export(job, overlays=overlays)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
