"""Past hourly weather from KNRS (Imperial Beach NOLF, in the river valley) via the Iowa Environmental Mesonet ASOS archive.

Station choice: KNRS at 32.5631,-117.1100 sits on the Tijuana River valley floor ~2 km from Nestor, so
it sees the same nighttime drainage winds as the hotspot. Brown Field (KSDM) is on the mesa and is the fallback.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

import numpy as np

from collectors.common import fetch
from config import PAST_WX_STATION
from db import store

URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
SKY = {"CLR": 0.0, "SKC": 0.0, "NSC": 0.0, "FEW": 0.19, "SCT": 0.44, "BKN": 0.75, "OVC": 1.0, "VV": 1.0}
UTC = timezone.utc


def parse_hourly(payload: bytes, station: str = PAST_WX_STATION) -> list[dict]:
    hours: dict[datetime, dict] = {}
    for r in csv.DictReader(io.StringIO(payload.decode())):
        try:
            t = datetime.strptime(r["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
        except (KeyError, ValueError):
            continue
        h = t.replace(minute=0)
        def num(k):
            v = r.get(k, "M")
            return None if v in ("M", "", None) else float(v)
        sky = [SKY.get(r.get(k, ""), None) for k in ("skyc1", "skyc2", "skyc3")]
        sky = [s for s in sky if s is not None]
        tmpc = num("tmpc")
        if tmpc is not None and tmpc < -5:  # KNRS logs a -16.67 C (2 F) placeholder; it never freezes here
            tmpc = None
        rec = {"sknt": num("sknt"), "drct": num("drct"), "tmpc": tmpc, "sky": max(sky) if sky else None}
        prev = hours.get(h)
        if prev is None or t.minute >= 50:  # prefer the routine :53 METAR
            hours[h] = rec
    if not hours:
        return []
    start, end = min(hours), max(hours)
    times = [start + timedelta(hours=i) for i in range(int((end - start).total_seconds() // 3600) + 1)]

    def series(key):
        a = np.array([hours.get(t, {}).get(key) if hours.get(t, {}).get(key) is not None else np.nan for t in times], float)
        idx = np.arange(len(a)); ok = np.isfinite(a)
        if ok.sum() == 0:
            return a
        return np.interp(idx, idx[ok], a[ok])  # fill gaps (KNRS has hourly gaps)

    sknt, tmpc, sky = series("sknt"), series("tmpc"), series("sky")
    # direction: calm reports (0 kt) carry no direction -> carry forward the last real one
    d = np.array([hours.get(t, {}).get("drct") if (hours.get(t, {}).get("sknt") or 0) > 0 else np.nan for t in times], float)
    last = 270.0
    for i in range(len(d)):
        if np.isfinite(d[i]):
            last = d[i]
        d[i] = last
    return [{"observed_at": t, "station": station, "kind": "observed", "issued_at": None,
             "wind_ms": float(sknt[i]) * 0.5144, "wind_dir_deg": float(d[i]), "temp_c": float(tmpc[i]),
             "cloud_frac": float(sky[i]) if np.isfinite(sky[i]) else 0.0} for i, t in enumerate(times)]


def backfill_weather(start: datetime, end: datetime, station: str = PAST_WX_STATION) -> int:
    """Idempotent: re-fetching overlapping ranges just upserts. Never refetches days already complete."""
    have = store.weather("observed", start, end, station)
    if len(have) >= int((end - start).total_seconds() // 3600) - 2:
        return 0
    params = {"station": station, "data": ["sknt", "drct", "tmpc", "skyc1", "skyc2", "skyc3"],
              "year1": start.year, "month1": start.month, "day1": start.day,
              "year2": end.year, "month2": end.month, "day2": end.day,
              "tz": "Etc/UTC", "format": "onlycomma", "latlon": "no", "missing": "M", "report_type": [3, 4]}
    payload = fetch(f"weather_archive_{station}", URL, ext="csv", params=params, timeout=120)
    return store.upsert_weather(parse_hourly(payload, station))


def refresh_recent(hours: int = 72) -> int:
    end = datetime.now(UTC) + timedelta(days=1)
    start = end - timedelta(hours=hours + 24)
    params = {"station": PAST_WX_STATION, "data": ["sknt", "drct", "tmpc", "skyc1", "skyc2", "skyc3"],
              "year1": start.year, "month1": start.month, "day1": start.day,
              "year2": end.year, "month2": end.month, "day2": end.day,
              "tz": "Etc/UTC", "format": "onlycomma", "latlon": "no", "missing": "M", "report_type": [3, 4]}
    payload = fetch(f"weather_archive_{PAST_WX_STATION}", URL, ext="csv", params=params,
                    min_interval=timedelta(minutes=30))
    return store.upsert_weather(parse_hourly(payload))


if __name__ == "__main__":
    store.init_db(); print("observed rows", refresh_recent())
