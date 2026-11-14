"""Tijuana River flow at the international boundary (USIBWC gauge 11-0133.00) -> daily mean MGD.

Verified Nov 14 2026: the public USIBWC Water Data Portal (Aquarius WebPortal) serves a CSV export with plain httpx,
after accepting its disclaimer page (a session cookie). Dataset "Discharge.Best Available@11013300" is 15-minute m^3/s,
history back to 2000-06. We average to daily means (portal time, fixed UTC-8) and convert to MGD.
USGS NWIS has no data for this site (11013300 not served, 11013500 returns empty), so the portal is the source.
Bright Data Web Unlocker is only a fallback when the direct fetch fails and a token is set.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import time
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta

import httpx

from collectors.common import brightdata_unlocker, save_raw
from config import USER_AGENT
from db import store

log = logging.getLogger("flow")
STATION = "11013300"
DATASET = f"Discharge.Best Available@{STATION}"
BASE = "https://waterdata.ibwc.gov/AQWebportal"
CMS_TO_MGD = 22.8245
CFS_TO_MGD = 0.64632
SOURCE = f"usibwc_{STATION}"
FIRST_DAY = date(2000, 6, 1)


def export_params(start: date, end: date) -> dict:
    return {"DataSet": DATASET, "ExportFormat": "csv", "Compressed": "true", "RoundData": "False", "Unit": "",
            "Timezone": "-8", "Calendar": "CUSTOM", "DateRange": "Custom",
            "StartTime": f"{start:%Y-%m-%d} 00:00", "EndTime": f"{end:%Y-%m-%d} 23:59"}


def unit_factor(header: str) -> float:
    h = header.lower()
    if "m^3" in h or "cms" in h:
        return CMS_TO_MGD
    if "ft^3" in h or "cfs" in h:
        return CFS_TO_MGD
    raise ValueError(f"unknown flow unit in header: {header!r}")


def parse_csv(text: str) -> list[dict]:
    """Portal export CSV (15-min readings) -> daily mean MGD rows. Lines starting with # or a quote are metadata."""
    lines = [l for l in text.splitlines() if l and l[0] not in '#"']
    reader = csv.reader(lines)
    header = next(reader, None)
    if not header or len(header) < 2:
        return []
    factor = unit_factor(header[1])
    sums: dict[date, list[float]] = defaultdict(lambda: [0.0, 0])
    for row in reader:
        if len(row) < 2 or not row[1].strip():
            continue
        try:
            d = datetime.fromisoformat(row[0].strip()[:19]).date()
            v = float(row[1])
        except ValueError:
            continue
        s = sums[d]; s[0] += v; s[1] += 1
    return [{"date": d, "mgd": round(s[0] / s[1] * factor, 2), "source": SOURCE} for d, s in sorted(sums.items())]


def parse_payload(body: bytes) -> list[dict]:
    if body[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".csv")]
            body = z.read(names[0]) if names else b""
    return parse_csv(body.decode("utf-8-sig", errors="replace"))


def _direct(start: date, end: date) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=300, follow_redirects=True) as c:
        r = c.get(f"{BASE}/Disclaimer"); r.raise_for_status()
        m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', r.text)
        time.sleep(1)
        r = c.post(f"{BASE}/AcceptDisclaimer", data={"__RequestVerificationToken": m.group(1) if m else "",
                                                      "returnUrl": "/AQWebportal/"})
        r.raise_for_status()
        time.sleep(1)
        r = c.get(f"{BASE}/Export/DataSet", params=export_params(start, end)); r.raise_for_status()
        return r.content


def _fetch_body(start: date, end: date) -> bytes:
    try:
        body = _direct(start, end)
        if not parse_payload(body):
            raise ValueError("export returned no rows")
        store.log_fetch("usibwc_flow", "ok", None, f"direct {start}..{end}")
        return body
    except Exception as e:
        log.warning("direct portal fetch failed (%s); trying Bright Data if configured", e)
        store.log_fetch("usibwc_flow", "error", None, str(e))
        url = httpx.URL(f"{BASE}/Export/DataSet", params=export_params(start, end))
        return brightdata_unlocker("usibwc_flow", str(url), "zip")  # raises RuntimeError without a token


def fetch_flow(days: int | None = None) -> int:
    """Incremental: from 3 days before the newest stored day, or the full history on first run."""
    have = store.flow_upto(date.today(), 1)
    if days is not None:
        start = date.today() - timedelta(days=days)
    elif have:
        start = date.fromisoformat(str(have[0]["date"])) - timedelta(days=3)
    else:
        start = FIRST_DAY
    try:
        body = _fetch_body(start, date.today())
    except Exception as e:
        log.warning("flow fetch skipped: %s", e)
        return 0
    save_raw("usibwc_flow", body, "zip" if body[:2] == b"PK" else "csv")
    rows = parse_payload(body)
    store.upsert_flow(rows)
    return len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    store.init_db(); print("flow rows", fetch_flow())
