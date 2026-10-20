from pathlib import Path

from hypercut import review
from hypercut.plan import EditPlan, Graphic, Segment, Source, Transcript, Word

SOURCE = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=20)


def _plan():
    return EditPlan(
        source=SOURCE, segments=[Segment(start=0, end=20)],
        transcript=Transcript(words=[Word(text="ten", start=5, end=5.5)]),
        graphics=[Graphic(id="g1", type="kinetic_text", start=4, end=7, props={"text": "TEN TIMES FASTER THAN EVER"}),
                  Graphic(id="g2", type="stat_card", start=12, end=14, props={"value": "10x"})],
    )


def test_samples_every_graphic_and_fills_gaps():
    times = review.sample_times(_plan())
    assert 5.5 in times and 13.0 in times and len(times) >= 4 and times == sorted(times)


def test_issues_come_with_validated_fixes(tmp_path):
    frames = [tmp_path / f"{i}.jpg" for i in range(len(review.sample_times(_plan())))]
    for f in frames:
        f.write_bytes(b"jpg")
    seen = {}

    def ask(prompt, system="", images=None, timeout=0):
        seen["n"], seen["prompt"] = len(images), prompt
        return {"summary": "Mostly clean.", "issues": [
            {"frame": 1, "severity": "high", "problem": "The title covers the mouth.", "ops": [{"op": "anchor", "key": "g1", "anchor": "top"}]},
            {"frame": 0, "problem": "Picture looks cheap.", "ops": [{"op": "cut", "start": 0, "end": 5}]},  # not a review op
        ]}

    result = review.review(_plan(), Path("unused.mp4"), ask=ask, frames=frames)
    assert seen["n"] == len(frames) and "g1 kinetic_text" in seen["prompt"]
    assert [i.severity for i in result.issues] == ["high", "low"] and result.issues[1].ops == []
    assert result.plan.graphics[0].anchor == "top" and result.summary == "Mostly clean."
    assert result.plan.segments == _plan().segments
