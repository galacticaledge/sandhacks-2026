"""NWS gridpoint forecast for Nestor (SGX 58,7): hourly wind, temperature, sky cover, 48 h+."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from collectors.common import fetch
from config import NWS_GRID
from db import store

URL = "https://api.weather.gov/gridpoints/{}/{},{}".format(*NWS_GRID)
STATION = "NWS_{}_{}_{}".format(*NWS_GRID)


def _duration_hours(d: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", d)
    if not m:
        return 1
    days, hours = int(m.group(1) or 0), int(m.group(2) or 0)
    return max(days * 24 + hours, 1)


def _expand(series: dict) -> dict[datetime, float]:
    out = {}
    for v in series.get("values", []):
        start, dur = v["validTime"].split("/")
        t0 = datetime.fromisoformat(start).astimezone(timezone.utc)
        for h in range(_duration_hours(dur)):
            out[t0 + timedelta(hours=h)] = v["value"]
    return out


def parse(payload: bytes) -> list[dict]:
    p = json.loads(payload)["properties"]
    issued = datetime.fromisoformat(p["updateTime"]).astimezone(timezone.utc)
    temp = _expand(p["temperature"])                 # degC
    ws = _expand(p["windSpeed"])                     # km/h
    wd = _expand(p["windDirection"])                 # degrees
    sky = _expand(p["skyCover"])                     # percent
    rows = []
    for t in sorted(set(temp) & set(ws) & set(wd)):
        rows.append({"observed_at": t, "station": STATION, "kind": "forecast", "issued_at": issued,
                     "wind_ms": (ws[t] or 0) / 3.6, "wind_dir_deg": wd[t] or 0, "temp_c": temp[t],
                     "cloud_frac": (sky.get(t) or 0) / 100})
    return rows


def fetch_nws_forecast() -> int:
    payload = fetch("nws_forecast", URL, headers={"Accept": "application/geo+json"},
                    min_interval=timedelta(minutes=50))
    return store.upsert_weather(parse(payload))


if __name__ == "__main__":
    store.init_db(); print("nws rows", fetch_nws_forecast())
