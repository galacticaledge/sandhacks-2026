"""Historical hourly H2S from SDAPCD's public Power BI dashboard via Bright Data Scraping Browser (spec 4, step 0).

The report (linked from SDAPCD's TJRV air-quality monitoring page) is loaded in a real browser session.
We change the report's own date slicer and record the data responses the page itself loads
(`.../public/reports/querydata`), cache them raw, and decode Power BI's compressed DSR format.

    python -m collectors.powerbi_history --months 6          # needs BRIGHTDATA_SCRAPING_BROWSER_WSS
    python -m collectors.powerbi_history --parse-cached      # re-decode cached responses, no network
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

from collectors.common import RAW_DIR, save_raw
from config import SDAPCD_POWERBI_URL, TZ, level_for
from db import store

log = logging.getLogger("powerbi")
SOURCE = "powerbi_history"
UTC = timezone.utc


def site_id_for(location: str) -> str | None:
    l = (location or "").lower()
    if "ysidro" in l:
        return "san_ysidro"
    if "nestor" in l or "berry" in l or "bes" in l:
        return "nestor_bes"
    if "ib" in l.split() or "imperial" in l or "civic" in l:
        return "ib_civic"
    return None


# ---------- DSR decoding ----------
def decode_dsr(result: dict) -> list[dict]:
    """Decode one querydata result into rows of {column_name: value}.

    Power BI compresses rows: 'S' gives the schema (once), 'C' the changed values, 'R' a bitmask of
    columns repeated from the previous row, 'Ø' a bitmask of null columns; strings come from ValueDicts."""
    data = result["result"]["data"]
    names = {s["Value"]: s.get("Name", s["Value"]) for s in data["descriptor"]["Select"]}
    ds = data["dsr"]["DS"][0]
    dicts = ds.get("ValueDicts", {})
    rows, schema, prev = [], None, None
    for ph in ds.get("PH", []):
        for dm in ph.values():
            for row in dm:
                if "S" in row:
                    schema = row["S"]
                if schema is None or "C" not in row and "R" not in row and "Ø" not in row:
                    continue
                vals = list(row.get("C", []))
                rep, nul = row.get("R", 0), row.get("Ø", 0)
                out = []
                for i, col in enumerate(schema):
                    if rep >> i & 1:
                        out.append(prev[i] if prev else None)
                    elif nul >> i & 1:
                        out.append(None)
                    else:
                        v = vals.pop(0) if vals else None
                        if "DN" in col and isinstance(v, int):
                            v = dicts[col["DN"]][v]
                        out.append(v)
                prev = out
                rows.append({names.get(col["N"], col["N"]): out[i] for i, col in enumerate(schema)})
    return rows


def to_readings(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        t = next((v for k, v in r.items() if "DATETIME" in k.upper() and isinstance(v, (int, float))), None)
        loc = next((v for k, v in r.items() if "LOCATION" in k.upper()), None)
        ppb = next((v for k, v in r.items() if "PPB" in k.upper()), None)
        sid = site_id_for(loc)
        if t is None or sid is None:
            continue
        # Power BI DateTimes are naive wall-clock times serialised as if UTC
        wall = datetime(1970, 1, 1) + timedelta(milliseconds=t)
        when = wall.replace(tzinfo=TZ).astimezone(UTC)
        ppb = float(ppb) if ppb is not None else None
        out.append({"observed_at": when, "site_id": sid, "ppb": ppb,
                    "level": level_for(max(ppb, 0)) if ppb is not None else None, "source": "powerbi_history"})
    return out


def parse_cached() -> int:
    d = RAW_DIR / SOURCE
    n = 0
    for p in sorted(d.glob("*.json")) if d.exists() else []:
        try:
            body = json.loads(p.read_text())
            for res in body.get("results", []):
                rows = to_readings(decode_dsr(res))
                # never overwrite live-feed rows with history rows for the same hour
                live = {(r["site_id"], r["observed_at"]) for r in store.readings(
                    min((x["observed_at"] for x in rows), default=datetime.now(UTC)),
                    max((x["observed_at"] for x in rows), default=datetime.now(UTC)) + timedelta(hours=1))
                    if r["source"] == "live_feed"}
                n += store.upsert_readings([r for r in rows if (r["site_id"], r["observed_at"]) not in live])
        except Exception:
            log.exception("could not decode %s", p.name)
    return n


# ---------- capture with Bright Data Scraping Browser ----------
async def capture(months: int = 6, headless_wait_ms: int = 8000) -> int:
    from playwright.async_api import async_playwright
    wss = os.getenv("BRIGHTDATA_SCRAPING_BROWSER_WSS")
    if not wss:
        raise RuntimeError("BRIGHTDATA_SCRAPING_BROWSER_WSS not set")
    saved = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(wss)
        page = await browser.new_page()

        async def on_response(resp):
            nonlocal saved
            if "querydata" in resp.url and resp.request.method == "POST":
                try:
                    body = await resp.body()
                    save_raw(SOURCE, body, "json")
                    saved += 1
                except Exception:
                    log.exception("capture failed")

        page.on("response", on_response)
        await page.goto(SDAPCD_POWERBI_URL, timeout=120_000)
        await page.wait_for_timeout(headless_wait_ms)
        # The report's DATE slicer is a between-dates slicer with two text inputs. Walk it back a month at a time.
        end = date.today()
        for m in range(months):
            start = end - timedelta(days=31)
            inputs = page.locator("input.date-slicer-datepicker, .date-slicer-range input")
            if await inputs.count() >= 2:
                for idx, d in ((0, start), (1, end)):
                    box = inputs.nth(idx)
                    await box.click(); await box.fill(d.strftime("%-m/%-d/%Y")); await box.press("Enter")
                await page.wait_for_timeout(headless_wait_ms)
            else:
                log.warning("date slicer inputs not found; captured only the default view")
                break
            end = start
        await browser.close()
    store.log_fetch(SOURCE, "ok" if saved else "error", None, f"captured {saved} querydata responses")
    return saved


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=6)
    ap.add_argument("--parse-cached", action="store_true")
    a = ap.parse_args()
    store.init_db()
    if not a.parse_cached:
        print("captured responses:", asyncio.run(capture(a.months)))
    print("rows stored:", parse_cached())
    print("history range:", store.reading_range())
