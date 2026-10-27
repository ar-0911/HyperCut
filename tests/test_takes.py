from hypercut.analyze import cuts
from hypercut.analyze.takes import retakes
from hypercut.plan import Transcript, Word


def _t(*lines, gap=0.6):
    """Words 0.3 s each, `gap` seconds between lines."""
    words, t = [], 0.0
    for line in lines:
        for text in line.split():
            words.append(Word(text=text, start=round(t, 2), end=round(t + 0.3, 2)))
            t += 0.35
        t += gap
    return Transcript(words=words)


def test_a_line_said_again_keeps_the_last_take():
    tr = _t("The first thing you need is a plan.", "The first thing you need is a real plan.", "Then you build.")
    (r,) = retakes(tr)
    assert r.text.startswith("The first thing") and r.kept_at == tr.words[8].start
    removed = cuts.cut_ranges(tr, 20, max_silence=5, remove_retakes=True)
    assert removed and removed[0][0] <= tr.words[0].start + 0.01 and removed[0][1] < tr.words[8].start


def test_a_stumble_between_takes_goes_too():
    tr = _t("Most people never start a business.", "Sorry.", "Most people never start a business.")
    (r,) = retakes(tr)
    assert r.end == tr.words[7].start  # through the "Sorry."


def test_false_starts():
    broken = _t("So the reason...", "So the reason this works is simple.")
    assert len(retakes(broken)) == 1
    inline = _t("So the reason so the reason this works is simple.")
    (r,) = retakes(inline)
    assert r.text == "So the reason" and r.end == inline.words[3].start


def test_repeats_that_are_not_retakes_stay():
    assert retakes(_t("No.", "No.")) == []  # too short
    assert retakes(_t("Start with the customer.", "Then build the thing.", "Start with the customer.")) == []
    far = _t("Start with the customer every time.", "Start with the customer every time.", gap=12)
    assert retakes(far) == []
    twice = _t("A line that is said.", "A line that is said.")
    assert all(a >= twice.words[-1].end for a, _ in cuts.cut_ranges(twice, 20, max_silence=5))  # off unless asked


def test_the_first_cut_says_it_cut_a_retake():
    from hypercut import explain
    from hypercut.plan import EditPlan, Source

    tr = _t("Hello there friends.", "The first thing you need is a plan.", "The first thing you need is a real plan.")
    duration = tr.words[-1].end + 0.5
    segments = cuts.build_segments(duration, cuts.cut_ranges(tr, duration, 0.35, remove_retakes=True), None, "cold_open")
    plan = EditPlan(source=Source(path="n.mp4", width=1920, height=1080, fps=30, duration=duration), transcript=tr,
                    segments=segments)
    kinds = [i["kind"] for i in explain.first_cut(plan)["items"]]
    assert "retake" in kinds
