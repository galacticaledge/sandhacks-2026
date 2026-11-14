"""What the web reported that night: verbatim news quotes fetched through Bright Data (collectors/web_reports.py)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Query

from config import TZ
from db import store

router = APIRouter(prefix="/api")
FIELDS = ("title", "source_name", "url", "published_at", "quote", "topic", "fetched_at", "via")


def _rows(first: date, last: date) -> list[dict]:
    """Reports published on Pacific-time dates first..last (inclusive), newest first."""
    a = datetime.combine(first, time.min, tzinfo=TZ)
    b = datetime.combine(last + timedelta(days=1), time.min, tzinfo=TZ)
    out = []
    for r in store.web_reports(a, b):
        row = {k: r.get(k) for k in FIELDS}
        for k in ("published_at", "fetched_at"):
            row[k] = row[k].isoformat() if row[k] else None
        out.append(row)
    return out


@router.get("/reports/recent")
def recent(days: int = Query(7, ge=1, le=60)):
    today = datetime.now(TZ).date()
    return _rows(today - timedelta(days=days), today)


@router.get("/reports")
def reports(night: date, days: int = Query(2, ge=0, le=14)):
    """Published from `night` to `days` after it: an evening spike is usually reported the next day."""
    return _rows(night, night + timedelta(days=days))
