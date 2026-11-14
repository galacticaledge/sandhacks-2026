"""Historical hourly H2S for the three SDAPCD monitors, from UCSD Resilient Shield's public yearly CSV files.

Same bucket and same row format as the live feed (collectors/h2s_feed.py), so the site names, units (ppb)
and timestamps line up with what we poll every 15 minutes.

    python -m collectors.h2s_history             # download once (cached), load, print a summary
    python -m collectors.h2s_history --refresh   # re-download the files first
    python -m collectors.h2s_history --summary   # only print the summary of what is in the database

Timestamps (checked 2026-11-14 against CARB AQMIS and SDAPCD's own air-data tool, see docs/data_status.md):
`Date with time` is the START of the hourly average and carries its own UTC offset, so converting it to
UTC is exact. Do not key rows on the local wall-clock text: the files switch offset by calendar day, so
around a clock change two different hours can share the same wall-clock text with different offsets.
"""
from __future__ import annotations

import argparse
import csv
import io
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from config import MONITOR_BY_FEED, MONITORS, ORANGE_PPB, RAW_DIR, TZ, USER_AGENT, level_for
from db import store

log = logging.getLogger("h2s_history")
UTC = timezone.utc
SOURCE = "resilient_history"
CACHE_DIR = RAW_DIR / "h2s_history"
BASE = "https://oss.resilientservice.mooo.com/resilentpublic/tijuana/sd_apcd_air/output/"
# Oldest first. Later files win if the same site-hour appears twice.
FILES = [
    "yearly/h2s/2024/apcd_h2s_2024.csv",
    "yearly/h2s/2025/apcd_h2s_2025.csv",
    "apcd_h2s_latest.csv",  # the current year so far, regenerated daily by Resilient Shield
]
NIGHT_START_HOUR, NIGHT_HOURS = 18, 15  # same window as validate/replay.py: 6 PM to 9 AM local


def download(refresh: bool = False) -> list[Path]:
    """Fetch each file once into data/raw/h2s_history/. Cached files are reused unless refresh=True."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    paths, fetched = [], 0
    for rel in FILES:
        p = CACHE_DIR / Path(rel).name
        if refresh or not p.exists() or p.stat().st_size == 0:
            if fetched:
                time.sleep(1.5)  # polite: under 1 request per second
            try:
                r = httpx.get(BASE + rel, headers={"User-Agent": USER_AGENT}, timeout=120, follow_redirects=True)
                r.raise_for_status()
            except Exception as e:
                store.log_fetch(SOURCE, "error", None, f"{rel}: {e}")
                raise
            tmp = p.with_suffix(".part")
            tmp.write_bytes(r.content)
            tmp.replace(p)
            fetched += 1
            store.log_fetch(SOURCE, "ok", str(p), f"downloaded {rel} ({len(r.content)} bytes)")
            log.info("downloaded %s (%d bytes)", rel, len(r.content))
        else:
            log.info("using cached %s", p.name)
        paths.append(p)
    return paths


def parse(payload: bytes | str) -> list[dict]:
    """One Resilient Shield H2S CSV -> reading rows (UTC hour start). Unknown sites are dropped.

    A blank Result or a Qualifier (e.g. '<', below detection / invalid) becomes ppb None, like the live feed."""
    text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        m = MONITOR_BY_FEED.get((r.get("SiteName") or "").strip())
        when = (r.get("Date with time") or "").strip()
        if not m or not when or "H2S" not in (r.get("Parameter") or "H2S").upper():
            continue
        t = datetime.fromisoformat(when)
        if t.tzinfo is None:
            raise ValueError(f"timestamp without UTC offset: {when}")
        raw = (r.get("Result") or "").strip()
        ppb = None if raw == "" or (r.get("Qualifier") or "").strip() else float(raw)
        rows.append({"observed_at": t.astimezone(UTC), "site_id": m.site_id, "ppb": ppb,
                     "level": level_for(max(ppb, 0.0)) if ppb is not None else None, "source": SOURCE})
    return rows


def merge(batches: list[list[dict]]) -> list[dict]:
    """One row per (site, UTC hour). A later batch wins, but a missing value never replaces a real one."""
    out: dict[tuple, dict] = {}
    for rows in batches:
        for r in rows:
            k = (r["site_id"], r["observed_at"])
            if r["ppb"] is None and k in out and out[k]["ppb"] is not None:
                continue
            out[k] = r
    return sorted(out.values(), key=lambda r: (r["observed_at"], r["site_id"]))


def load(paths: list[Path], chunk: int = 5000) -> int:
    rows = merge([parse(p.read_bytes()) for p in paths])
    if not rows:
        return 0
    # the live feed is the fresher copy of the same data: never overwrite its rows
    live = {(r["site_id"], r["observed_at"]) for r in store.readings(
        rows[0]["observed_at"], rows[-1]["observed_at"] + timedelta(hours=1)) if r["source"] == "live_feed"}
    rows = [r for r in rows if (r["site_id"], r["observed_at"]) not in live]
    n = 0
    for i in range(0, len(rows), chunk):
        n += store.upsert_readings(rows[i:i + chunk])
    return n


def night_of(t: datetime):
    """Date of the evening a reading belongs to (6 PM to 9 AM local), or None for daytime hours."""
    local = t.astimezone(TZ)
    start = local.replace(hour=NIGHT_START_HOUR, minute=0, second=0, microsecond=0)
    if local < start:
        start -= timedelta(days=1)
    return start.date() if (t - start.astimezone(UTC)) < timedelta(hours=NIGHT_HOURS) else None


def summary() -> dict[str, dict]:
    """Per site, straight from the database: rows, valid hours, range, orange hours and orange nights."""
    a, b, _ = store.reading_range()
    out = {}
    if not a:
        return out
    by_site = defaultdict(list)
    for r in store.readings(a, b + timedelta(hours=1)):
        by_site[r["site_id"]].append(r)
    for m in MONITORS:
        rs = by_site.get(m.site_id, [])
        valid = [r for r in rs if r["ppb"] is not None]
        orange = [r for r in valid if r["ppb"] >= ORANGE_PPB]
        src = defaultdict(int)
        for r in rs:
            src[r["source"]] += 1
        out[m.site_id] = {
            "rows": len(rs), "valid_hours": len(valid), "by_source": dict(src),
            "first": min((r["observed_at"] for r in valid), default=None),
            "last": max((r["observed_at"] for r in valid), default=None),
            "orange_hours": len(orange),
            "orange_days": len({r["observed_at"].astimezone(TZ).date() for r in orange}),
            "orange_nights": len({night_of(r["observed_at"]) for r in orange} - {None}),
            "max_ppb": max((r["ppb"] for r in valid), default=None),
        }
    return out


def print_summary():
    for sid, s in summary().items():
        fmt = lambda t: t.astimezone(TZ).strftime("%Y-%m-%d %H:%M %Z") if t else "-"
        print(f"{sid:11s} rows={s['rows']:6d} valid_hours={s['valid_hours']:6d} "
              f"first={fmt(s['first'])} last={fmt(s['last'])} "
              f">={ORANGE_PPB:g}ppb: hours={s['orange_hours']} nights={s['orange_nights']} days={s['orange_days']} "
              f"max={s['max_ppb']} sources={s['by_source']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true", help="re-download even if cached")
    ap.add_argument("--summary", action="store_true", help="print the database summary only")
    a = ap.parse_args()
    store.init_db()
    if not a.summary:
        print("rows upserted:", load(download(a.refresh)))
    print_summary()
