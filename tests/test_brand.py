import pytest

from hypercut import brand
from hypercut.plan import Brand, EditPlan, Source, Style


def _plan():
    return EditPlan(source=Source(path="n.mp4", width=1920, height=1080, fps=30, duration=20),
                    style=Style(mode="podcast", pacing={"keep_pause": 0.12}))


def _kit(tmp_path, **brand_fields):
    folder = tmp_path / "kit"
    look = Style(caption={"font": "Inter", "color": "#111111"}, graphics={"accent_color": "#FF5A4E"},
                 transitions={"style": "hard"}, pacing={"keep_pause": 0.4})
    folder.mkdir()
    (folder / "logo.png").write_bytes(b"png")
    (folder / "music.mp3").write_bytes(b"mp3")
    brand.save(brand.Kit(name="Acme", look=brand.look_of(look),
                         brand=Brand(logo="logo.png", music="music.mp3", end_card="Follow Acme", **brand_fields)), folder)
    return folder


def test_apply_puts_the_look_and_files_on_the_reel(tmp_path):
    plan, job = _plan(), tmp_path / "job"
    job.mkdir()
    changes = brand.apply(plan, _kit(tmp_path), job)
    assert plan.style.caption.font == "Inter" and plan.style.graphics.accent_color == "#FF5A4E"
    assert plan.style.transitions.style == "hard"
    # How the reel is edited stays its own.
    assert plan.style.mode == "podcast" and plan.style.pacing.keep_pause == 0.12
    assert plan.brand.name == "Acme" and plan.brand.logo.startswith("brand-") and (job / plan.brand.logo).read_bytes() == b"png"
    assert plan.brand.music and plan.brand.end_card == "Follow Acme"
    assert changes[0] == "Applied the brand kit “Acme”" and "Logo in the corner" in changes


def test_a_kit_font_names_the_caption_font(tmp_path):
    folder = _kit(tmp_path, font="font.ttf", font_name="Acme Sans")
    (folder / "font.ttf").write_bytes(b"ttf")
    plan, job = _plan(), tmp_path / "job"
    job.mkdir()
    brand.apply(plan, folder, job)
    assert plan.style.caption.font == "Acme Sans" and plan.brand.font.endswith(".ttf")


def test_missing_files_are_dropped_not_fatal(tmp_path):
    folder = _kit(tmp_path)
    (folder / "music.mp3").unlink()
    plan, job = _plan(), tmp_path / "job"
    job.mkdir()
    brand.apply(plan, folder, job)
    assert plan.brand.music is None and plan.brand.logo


def test_file_checks():
    brand.check_file("logo", "a.PNG", 10)
    with pytest.raises(ValueError, match="must be one of"):
        brand.check_file("music", "a.exe", 10)
    with pytest.raises(ValueError, match="over"):
        brand.check_file("font", "a.ttf", 10**8)


def test_old_plans_have_no_brand():
    assert EditPlan.model_validate({"source": {"path": "n.mp4", "width": 1, "height": 1, "fps": 30, "duration": 1}}).brand == Brand()


def test_assistant_brand_op_and_diff():
    from hypercut import assistant, diff

    plan = _plan()
    plan.brand = Brand(logo="brand-1.png", music="brand-2.mp3", end_card="Follow")
    ops = [{"op": "brand", "logo_corner": "bottom_left", "music_volume": 3, "remove": ["end_card"]}]
    new, changes = assistant.apply_ops(plan, ops, playhead=0, assets=[])
    assert new.brand.logo_corner == "bottom_left" and new.brand.music_volume == 1.0 and new.brand.end_card == ""
    assert "Removed the end card" in changes and any(c.startswith("Logo: bottom left") for c in changes)
    assert "Removed the end card" in diff.explain(plan, new)
