from datetime import date
from pathlib import Path

from collectors import announcements as a

SAMPLE = (Path(__file__).parent / "fixtures" / "usibwc_press_releases_sample.html").read_text()


def test_parse_list_extracts_url_title_date():
    items = a.parse_list(SAMPLE)
    assert len(items) == 6
    h = next(i for i in items if "HEAVY-WASTEWATER" in i["url"])
    assert h["published"] == date(2026, 6, 2)
    assert h["title"] == "USIBWC handles heavy wastewater flows during Tijuana pipeline repair"
    assert h["url"].startswith("https://www.ibwc.gov/wp-content/uploads/2026/06/")


def test_select_filters_date_host_and_keywords():
    got = {i["title"] for i in a.select(a.parse_list(SAMPLE))}
    assert got == {"USIBWC handles heavy wastewater flows during Tijuana pipeline repair",
                   "CILA SUSPENDS PBCILA PUMP STATION OPERATIONS"}  # not 2023, not external, not Colorado River


def test_no_gemini_key_still_caches_text(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(a, "BASE", tmp_path)
    monkeypatch.setattr(a, "SEEN", tmp_path / "seen.txt")
    monkeypatch.setattr(a.time, "sleep", lambda s: None)
    monkeypatch.setattr(a, "save_raw", lambda *args, **kw: tmp_path / "x")
    monkeypatch.setattr(a, "_text", lambda body, url: "body text")
    monkeypatch.setattr(a, "_get", lambda src, url, ext: SAMPLE.encode() if src == "announcements_list" else b"%PDF-fake")
    assert a.fetch_announcements() == 0
    texts = sorted((tmp_path / "text").glob("*.txt"))
    assert len(texts) == 2 and "body text" in texts[0].read_text()
    assert not (tmp_path / "seen.txt").read_text().strip()  # nothing marked extracted
