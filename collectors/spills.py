"""USIBWC spill events by site (Resilient Shield geojson)."""
from __future__ import annotations

import json
from datetime import timedelta

from collectors.common import fetch
from db import store

URL = "https://oss.resilientservice.mooo.com/resilentpublic/tijuana/ibwc/output/spills_last_by_site.geojson"


def parse(payload: bytes) -> list[dict]:
    rows = {}
    for f in json.loads(payload)["features"]:
        p = f["properties"]
        site = p.get("Discharge Location") or f.get("id")
        rows[site] = {"site": site, "lat": p.get("Latitude"), "lon": p.get("Longitude"),
                      "start_date": p.get("Start Date"), "end_date": p.get("End Date"),
                      "event_type": p.get("Event Type"), "volume": p.get("Approximate Discharge Volume"),
                      "notes": p.get("Notes")}
    return list(rows.values())


def poll_spills() -> int:
    rows = parse(fetch("spills", URL, ext="geojson", min_interval=timedelta(minutes=30)))
    store.replace_spills(rows)
    return len(rows)


if __name__ == "__main__":
    store.init_db(); print("spills", poll_spills())
