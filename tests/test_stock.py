import pytest

from hypercut.generate import stock


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "pk")
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    monkeypatch.delenv("HYPERCUT_STOCK", raising=False)


def test_pexels_clips_come_first_with_the_best_fitting_file(monkeypatch):
    def http_json(method, url, headers=None, body=None, params=None):
        assert headers == {"Authorization": "pk"} and params["orientation"] == "portrait"
        if "videos" in url:
            return {"videos": [{"url": "https://www.pexels.com/video/aerial-view-of-a-city-123/", "image": "thumb.jpg",
                                "duration": 12, "user": {"name": "Ana"},
                                "video_files": [{"link": "4k.mp4", "width": 2160, "height": 3840},
                                                {"link": "hd.mp4", "width": 1080, "height": 1920},
                                                {"link": "sd.mp4", "width": 540, "height": 960}]}]}
        return {"photos": [{"url": "https://p/1", "photographer": "Bo", "alt": "city", "src": {"medium": "m.jpg", "large2x": "l.jpg"}}]}

    monkeypatch.setattr(stock, "http_json", http_json)
    found = stock.search("city at night", "any")
    assert [c.kind for c in found] == ["video", "image"]
    assert found[0].url == "hd.mp4" and found[0].title == "aerial view of a city" and found[0].credit == "Ana / Pexels"
    assert not found[0].credit_required


def test_commons_keeps_only_open_licences_and_credits_cc_by(monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY")
    monkeypatch.setenv("HYPERCUT_STOCK", "commons")

    def page(title, licence, artist="<a href='x'>Jane</a>"):
        return {"title": f"File:{title}.jpg", "imageinfo": [{"thumburl": f"{title}.jpg", "descriptionurl": "d",
                "extmetadata": {"LicenseShortName": {"value": licence}, "Artist": {"value": artist}}}]}

    monkeypatch.setattr(stock, "http_json", lambda *a, **k: {"query": {"pages": {
        "1": page("Skyline", "CC BY 4.0"), "2": page("Shared", "CC BY-SA 4.0"), "3": page("Old", "Public domain"),
        "4": page("NC", "CC BY-NC 2.0")}}})
    found = stock.search("skyline", "image")
    assert [c.title for c in found] == ["Skyline", "Old"]
    assert found[0].credit_required and found[0].credit == "Jane, CC BY 4.0, Wikimedia Commons"
    assert not found[1].credit_required
    assert stock.search("skyline", "video") == []


def test_choose_shows_claude_the_thumbnails(monkeypatch, tmp_path):
    cands = [stock.Candidate("pexels", "video", f"shot {i}", f"t{i}", f"u{i}", "c", "") for i in range(3)]
    monkeypatch.setattr(stock, "download", lambda url, out, headers=None: out.write_bytes(b"jpg") and out)
    seen = {}

    def ask(prompt, images=None, **kw):
        seen["images"], seen["prompt"] = images, prompt
        return {"pick": 2}

    assert stock.choose(cands, "a busy kitchen", "we cook", ask=ask) is cands[2]
    assert len(seen["images"]) == 3 and "a busy kitchen" in seen["prompt"]
    assert stock.choose(cands, "x", ask=lambda p, images=None, **k: {"pick": None}) is None
    assert stock.choose([], "x") is None
