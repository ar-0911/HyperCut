from hypercut import edit, suggest
from hypercut.plan import EditPlan, Hook, HookCandidate, Segment, Source, Transcript, Word

SOURCE = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=80)


def _words(n, gap=0.0):
    words, t = [], 0.0
    for i in range(n):
        words.append(Word(text=f"w{i}." if i % 5 == 4 else f"w{i}", start=t, end=t + 0.5))
        t += 0.5 + (gap if i % 5 == 4 else 0.0)
    return words


def _plan(seconds, candidates=None, chosen=0, gap=0.0):
    words = _words(int(seconds * 2), gap)
    end = words[-1].end
    return EditPlan(source=SOURCE.model_copy(update={"duration": end + 1}), transcript=Transcript(words=words),
                    hook=Hook(candidates=candidates or [], chosen=chosen),
                    segments=[Segment(start=0, end=end, reason="body")])


def test_a_long_reel_gets_a_shorter_cut():
    plan = _plan(70)
    found = suggest.suggest(plan)
    assert found.kind == "shorter"
    assert edit.reel_duration(found.plan) <= suggest.SHORTER + 0.5  # plus the pause after the last word
    assert found.changes


def test_a_close_second_hook_is_offered():
    plan = _plan(30, [HookCandidate(start=0, end=2, text="first", score=0.9),
                      HookCandidate(start=10, end=12, text="the close one", score=0.8),
                      HookCandidate(start=20, end=22, text="far behind", score=0.3)])
    found = suggest.suggest(plan)
    assert found.kind == "hook" and found.plan.hook.chosen == 1 and "close one" in found.why


def test_long_pauses_get_tightened():
    plan = _plan(30, gap=1.0)  # a second of silence after every sentence, kept by the plan
    found = suggest.suggest(plan)
    assert found.kind == "tighter"
    assert edit.reel_duration(found.plan) < edit.reel_duration(plan) - 1
    assert len(found.plan.transcript.words) == len(plan.transcript.words)


def test_nothing_to_suggest():
    plan = _plan(30)
    plan.style.pacing.max_silence, plan.style.pacing.keep_pause = 0.2, 0.05
    assert suggest.suggest(plan) is None
