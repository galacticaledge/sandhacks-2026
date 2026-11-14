"""/api/reports response shape and date window (no database: store.web_reports is stubbed)."""
from datetime import date, datetime, timezone

from api.routes import reports

ROW = {"id": "wr-1", "url": "https://www.kpbs.org/x", "source_name": "KPBS", "title": "T",
       "published_at": datetime(2026, 3, 20, 18, 33, tzinfo=timezone.utc), "quote": "Q" * 30, "topic": "odor",
       "fetched_at": datetime(2026, 11, 14, 22, 0, tzinfo=timezone.utc), "via": "brightdata_unlocker",
       "search_query": "s"}


def test_reports_shape_and_window(monkeypatch):
    seen = {}

    def fake(a, b):
        seen["a"], seen["b"] = a, b
        return [dict(ROW)]

    monkeypatch.setattr(reports.store, "web_reports", fake)
    out = reports.reports(night=date(2026, 3, 19), days=2)
    assert list(out[0]) == ["title", "source_name", "url", "published_at", "quote", "topic", "fetched_at", "via"]
    assert out[0]["published_at"] == "2026-03-20T18:33:00+00:00" and out[0]["via"] == "brightdata_unlocker"
    # Pacific-time dates 03-19 .. 03-21 inclusive
    assert seen["a"].isoformat() == "2026-03-19T00:00:00-07:00" and seen["b"].isoformat() == "2026-03-22T00:00:00-07:00"
    assert reports.recent(days=7) == out
