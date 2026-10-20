from hypercut import edit, variants
from hypercut.plan import EditPlan, Hook, HookCandidate, Segment, Source, Transcript, Word

SOURCE = Source(path="n.mp4", width=1920, height=1080, fps=30, duration=60)


def _plan():
    # A sentence every 6 s: "w0 w1 end." ... ; one filler gap cut at 20-21.
    words = []
    for i in range(10):
        words += [Word(text="say", start=i * 6, end=i * 6 + 1), Word(text="it.", start=i * 6 + 2, end=i * 6 + 3)]
    hooks = [HookCandidate(start=12, end=15, text="first", score=0.9), HookCandidate(start=30, end=33, text="second", score=0.7)]
    segs = [Segment(start=12, end=15, reason="hook"), Segment(start=0, end=20, reason="body"), Segment(start=21, end=58, reason="body")]
    return EditPlan(source=SOURCE, transcript=Transcript(words=words), hook=Hook(candidates=hooks), segments=segs)


def test_rehook_keeps_the_body_cuts_and_ending():
    p = variants.rehook(_plan(), 1)
    assert p.hook.chosen == 1
    assert [(s.start, s.end, s.reason) for s in p.segments] == [(30, 33, "hook"), (0, 20, "body"), (21, 58, "body")]


def test_trim_ends_on_a_full_sentence_in_time():
    p = variants.trim_to(_plan(), 30)
    assert edit.reel_duration(p) <= 30
    last = p.segments[-1]
    assert last.reason == "body" and 26 <= last.end <= 27.5  # "it." ending at 27 (plus the short tail)
    assert variants.trim_to(_plan(), 600) is None


def test_variants_list_other_hooks_then_shorter_cuts():
    labels = [label for label, _ in variants.variants(_plan())]
    assert labels[0].startswith("Hook 2") and any(l.endswith("s cut") for l in labels)
