"""Tijuana River flow at the international boundary (USIBWC gauge 11-0133.00) via Bright Data Web Unlocker.

Status: export URL pattern is the standard Aquarius WebPortal CSV export -- TO VERIFY against the live portal.
Falls back to DEFAULT_FLOW_MGD (flagged "assumed default" in every forecast) when unavailable.
"""
from __future__ import annotations

import csv
import io
import logging
import os
from datetime import date, datetime, timedelta

from collectors.common import brightdata_unlocker
from db import store

log = logging.getLogger("flow")
STATION = "11013300"
PORTAL = os.getenv("USIBWC_EXPORT_URL", "https://waterdata.ibwc.gov/AQWebportal/Export/DataSet")
CMS_TO_MGD = 22.8245
CFS_TO_MGD = 0.646317


def export_url(start: date, end: date) -> str:
    return (f"{PORTAL}?DataSet=Discharge.Daily%20Mean@{STATION}&ExportFormat=csv&Compressed=false"
            f"&RoundData=False&Unit=&Timezone=-8&Calendar=CUSTOM&StartTime={start:%Y-%m-%d}%2000%3A00"
            f"&EndTime={end:%Y-%m-%d}%2023%3A59&DateRange=Custom")


def parse_csv(text: str) -> list[dict]:
    lines = [l for l in text.splitlines() if l and not l.startswith("#")]
    reader = csv.reader(io.StringIO("\n".join(lines)))
    header = next(reader, [])
    unit_factor = CMS_TO_MGD if any("m^3" in h or "cms" in h.lower() for h in header) else (
        CFS_TO_MGD if any("ft^3" in h or "cfs" in h.lower() for h in header) else 1.0)
    out = {}
    for row in reader:
        if len(row) < 2:
            continue
        try:
            t = datetime.fromisoformat(row[0].strip()[:19])
            v = float(row[-1]) if row[-1].strip() else float(row[1])
        except ValueError:
            continue
        out[t.date()] = v * unit_factor
    return [{"date": d, "mgd": round(v, 2), "source": f"usibwc_{STATION}"} for d, v in sorted(out.items())]


def fetch_flow(days: int = 120) -> int:
    have = store.flow_upto(date.today(), 1)
    start = date.fromisoformat(str(have[0]["date"])) - timedelta(days=2) if have else date.today() - timedelta(days=days)
    try:
        body = brightdata_unlocker("usibwc_flow", export_url(start, date.today()), "csv")
    except RuntimeError as e:
        log.warning("flow fetch skipped: %s", e)
        return 0
    rows = parse_csv(body.decode(errors="replace"))
    store.upsert_flow(rows)
    return len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    store.init_db(); print("flow rows", fetch_flow())
