"""SDAPCD odor complaints (Resilient Shield geojson). South Bay only."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from collectors.common import fetch
from db import store

URL = "https://oss.resilientservice.mooo.com/resilentpublic/latest/tijuana/sd_complaints/complaints.geojson"
BOX = (32.52, 32.62, -117.16, -116.98)


def parse(payload: bytes) -> list[dict]:
    out = []
    for f in json.loads(payload)["features"]:
        p, g = f["properties"], f.get("geometry") or {}
        if not g or g.get("type") != "Point":
            continue
        lon, lat = g["coordinates"][:2]
        if not (BOX[0] <= lat <= BOX[1] and BOX[2] <= lon <= BOX[3]):
            continue
        ms = p.get("date_and_time_received") or p.get("date_received")
        if ms is None:
            continue
        out.append({"record_number": p.get("record_number") or f.get("id"),
                    "received_at": datetime.fromtimestamp(ms / 1000, tz=timezone.utc),
                    "nature": p.get("nature_of_complaint") or "", "city": p.get("city") or "",
                    "lat": float(lat), "lon": float(lon)})
    return out


def poll_complaints() -> int:
    rows = parse(fetch("complaints", URL, ext="geojson", min_interval=timedelta(minutes=30)))
    store.upsert_complaints(rows)
    return len(rows)


if __name__ == "__main__":
    store.init_db(); print("complaints", poll_complaints())
