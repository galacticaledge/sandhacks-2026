"""web_reports: parsers on small saved fixtures, the verbatim-quote check, and one offline end-to-end run."""
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from collectors import web_reports as w

FIX = Path(__file__).parent / "fixtures"
ARTICLE = (FIX / "web_reports_kpbs_article.html").read_text()
SITEMAP = (FIX / "web_reports_kpbs_sitemap.xml").read_text()
WP_POSTS = (FIX / "web_reports_wp_posts.json").read_text()
KPBS_URL = ("https://www.kpbs.org/news/environment/2026/03/20/"
            "high-heat-broken-pump-lead-to-elevated-sewer-gas-smells-in-south-bay")
READING = ("The teams monitoring the South Bay found peaks as high as 4,500 ppb and up to an average of 2,100 ppb "
           "for one hour — peaking at night, when winds die down.")


def test_kpbs_sitemap_keeps_on_topic_urls_in_window():
    hits = w.parse_kpbs_sitemap(SITEMAP, date(2026, 3, 17), date(2026, 3, 23))
    assert [h["url"] for h in hits] == [KPBS_URL]          # /place/, off-topic slug and 03-06 are all dropped
    assert hits[0]["listed_date"] == date(2026, 3, 20)
    assert len(w.parse_kpbs_sitemap(SITEMAP, date(2026, 3, 1), date(2026, 3, 23))) == 2


def test_wp_posts_filtered_by_listed_date():
    hits = w.parse_wp_posts(WP_POSTS, date(2026, 3, 17), date(2026, 3, 21))
    assert [h["url"] for h in hits] == ["https://voiceofsandiego.org/2026/03/20/inside-the-debate-over-secret-county-subcommittees/"]
    assert w.parse_wp_posts("<html>blocked</html>", date(2026, 3, 17), date(2026, 3, 21)) == []


def test_search_urls_are_date_bounded_and_on_allowed_hosts():
    assert [u for u, _, _ in w.search_urls("www.kpbs.org", date(2025, 12, 30), date(2026, 1, 2))] == [
        "https://www.kpbs.org/sitemap-202512.xml", "https://www.kpbs.org/sitemap-202601.xml"]
    (url, ext, label), = w.search_urls("voiceofsandiego.org", date(2026, 3, 17), date(2026, 3, 23))
    assert "after=2026-03-17T00:00:00&before=2026-03-24T00:00:00" in url and "search=Tijuana" in url
    (url, _, _), = w.search_urls("timesofsandiego.com", date(2026, 3, 17), date(2026, 3, 23))
    assert "tags=" in url and "search=" not in url
    for host in w.SITES:
        assert not host.endswith(".gov") and "reddit" not in host


def test_article_title_date_and_text_come_from_the_page():
    art = w.parse_article(ARTICLE)
    assert art["title"] == "High heat, broken pump lead to elevated 'sewer gas' smells in South Bay"
    # JSON-LD carries an offset and wins over the offset-less meta tag
    assert art["published_at"] == datetime(2026, 3, 20, 18, 33, 20, tzinfo=timezone.utc)
    assert art["text"].count("\n") == 1 and "Navigation" not in art["text"] and "Footer" not in art["text"]
    assert w.is_relevant(art["text"]) and not w.is_relevant("City council votes on Tijuana trolley budget.")


def test_published_date_fallbacks():
    assert w.parse_published('<meta property="article:published_time" content="2026-04-06T12:17:31-07:00">') \
        .astimezone(timezone.utc) == datetime(2026, 4, 6, 19, 17, 31, tzinfo=timezone.utc)
    naive = w.parse_published('<meta property="article:published_time" content="2026-04-06T12:17:31">')
    assert naive.utcoffset().total_seconds() == -7 * 3600   # read as Pacific
    assert w.parse_published("<html><p>no date here</p></html>") is None


def test_verbatim_returns_page_text_or_nothing():
    text = w.parse_article(ARTICLE)["text"]
    assert w.verbatim(READING, text) == READING
    assert w.verbatim(READING.replace("—", "-").replace("  ", " "), text) == READING   # page's own characters back
    assert w.verbatim(READING.replace("4,500", "5,400"), text) is None                  # a changed number
    assert w.verbatim(READING.replace("found peaks", "saw peaks"), text) is None        # a paraphrase
    assert w.verbatim("4,500 ppb", text) is None                                        # too short to be a sentence


def test_pick_quote_skips_invented_candidates_and_fixes_reading_label():
    text = w.parse_article(ARTICLE)["text"]
    got = w.pick_quote([{"quote": "Levels hit 9,999 ppb in Imperial Beach on Friday night.", "topic": "h2s_reading"},
                        {"quote": READING, "topic": "h2s_reading"}], text)
    assert got == {"quote": READING, "topic": "h2s_reading"}
    first = text.split("\n")[0]
    assert w.pick_quote([{"quote": first, "topic": "h2s_reading"}], text)["topic"] == "other"  # no number in it
    assert w.pick_quote([{"quote": "Nothing like this is in the article at all.", "topic": "odor"}], text) is None


@pytest.fixture
def offline(tmp_path, monkeypatch):
    """No network, no Gemini, no database: bd_get serves fixtures, rows are captured in a list."""
    rows, calls = [], []
    pages = {"https://www.kpbs.org/sitemap-202603.xml": SITEMAP, KPBS_URL: ARTICLE}

    def fake_get(url, ext="html", max_age=None):
        calls.append(url)
        if url not in pages:
            raise RuntimeError("not in fixture set")
        return pages[url].encode(), datetime(2026, 11, 14, 22, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(w, "BASE", tmp_path)
    monkeypatch.setattr(w, "REQUESTS", tmp_path / "requests.jsonl")
    monkeypatch.setattr(w, "bd_get", fake_get)
    monkeypatch.setattr(w.store, "upsert_web_report", rows.append)
    monkeypatch.setattr(w.store, "log_fetch", lambda *a, **k: None)
    return rows, calls


def test_fetch_reports_stores_only_verified_rows(offline, monkeypatch):
    rows, _ = offline
    monkeypatch.setattr(w, "gemini_candidates", lambda text, url: [{"quote": READING, "topic": "h2s_reading"}])
    stats = w.fetch_reports(date(2026, 3, 17), date(2026, 3, 21))
    assert stats["stored"] == 1 and len(rows) == 1
    r = rows[0]
    assert r["url"] == KPBS_URL and r["source_name"] == "KPBS" and r["via"] == "brightdata_unlocker"
    assert r["quote"] == READING and r["topic"] == "h2s_reading" and r["id"] == w.report_id(KPBS_URL)
    assert r["published_at"] == datetime(2026, 3, 20, 18, 33, 20, tzinfo=timezone.utc)
    assert r["fetched_at"] == datetime(2026, 11, 14, 22, 0, tzinfo=timezone.utc) and "sitemap" in r["search_query"]


def test_fetch_reports_drops_unverifiable_quote_and_wrong_date(offline, monkeypatch):
    rows, _ = offline
    monkeypatch.setattr(w, "gemini_candidates", lambda text, url: [{"quote": "Readings reached 800 ppb overnight in Nestor.", "topic": "h2s_reading"}])
    assert w.fetch_reports(date(2026, 3, 17), date(2026, 3, 21))["no_verbatim_quote"] == 1
    # the sitemap URL date says 03-06 for the ranch story, but only pages whose own date is in the window count
    monkeypatch.setattr(w, "parse_published", lambda page: datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert w.fetch_reports(date(2026, 3, 17), date(2026, 3, 21))["wrong_date"] == 1
    assert rows == []


def test_bd_get_refuses_hosts_not_on_the_list(tmp_path, monkeypatch):
    monkeypatch.setattr(w, "BASE", tmp_path)
    monkeypatch.setattr(w, "INDEX", tmp_path / "index.jsonl")
    for url in ("https://www.ibwc.gov/press-releases/", "https://www.reddit.com/r/sandiego/", "https://www.google.com/search?q=x"):
        with pytest.raises(ValueError):
            w.bd_get(url)


def test_bd_get_serves_cache_without_a_request(tmp_path, monkeypatch):
    monkeypatch.setattr(w, "BASE", tmp_path)
    monkeypatch.setattr(w, "INDEX", tmp_path / "index.jsonl")
    monkeypatch.setattr(w, "REQUESTS", tmp_path / "requests.jsonl")
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "a.html").write_text("cached body")
    (tmp_path / "index.jsonl").write_text('{"url": "%s", "file": "pages/a.html", "fetched_at": "2026-11-14T22:00:00+00:00", "via": "brightdata_unlocker"}\n' % KPBS_URL)
    monkeypatch.setattr(w.httpx, "post", lambda *a, **k: pytest.fail("cached URL must not be refetched"))
    body, at = w.bd_get(KPBS_URL)
    assert body == b"cached body" and at.isoformat() == "2026-11-14T22:00:00+00:00" and w.request_count() == 0
