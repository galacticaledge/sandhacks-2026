"""Live H2S from UCSD Resilient Shield (SDAPCD monitors). Polled at most every 15 minutes."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from collectors.common import fetch
from config import MONITOR_BY_FEED, level_for
from db import store

URL = "https://oss.resilientservice.mooo.com/resilentpublic/tijuana/sd_apcd_air/output/hs2_lastday.records.json"


def parse(payload: bytes) -> list[dict]:
    rows = []
    for r in json.loads(payload)["data"]:
        m = MONITOR_BY_FEED.get(r.get("SiteName"))
        if not m:
            continue
        ppb = r.get("Result")
        ppb = None if ppb is None or r.get("Qualifier") else float(ppb)
        t = datetime.fromisoformat(r["Date with time"]).astimezone(timezone.utc)
        rows.append({"observed_at": t, "site_id": m.site_id, "ppb": ppb,
                     "level": level_for(max(ppb, 0.0)) if ppb is not None else None, "source": "live_feed"})
    return rows


def poll_h2s() -> int:
    return store.upsert_readings(parse(fetch("h2s_feed", URL, min_interval=timedelta(minutes=15))))


if __name__ == "__main__":
    store.init_db()
    print("rows", poll_h2s())
