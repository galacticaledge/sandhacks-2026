"""Assemble model inputs from the database: meteorology, river flow, observations."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import numpy as np

from collectors.nws import STATION as NWS_STATION
from config import DATA_DIR, DEFAULT_FLOW_MGD, MONITORS, PAST_WX_STATION, TZ
from db import store
from model.met import Met

UTC = timezone.utc
CALIBRATION_PATH = DATA_DIR / "calibration.json"


def hours(start: datetime, n: int) -> list[datetime]:
    return [start + timedelta(hours=i) for i in range(n)]


def assemble_met(times: list[datetime], prefer: list[str], issued_before: datetime | None = None) -> tuple[Met, list[str]]:
    """prefer: ordered kinds, e.g. ['observed','forecast']. Missing hours fall back down the list, then
    to the nearest available hour (persistence)."""
    a, b = times[0], times[-1] + timedelta(hours=1)
    pools = {}
    for kind in set(prefer):
        rows = store.weather(kind, a - timedelta(hours=6), b + timedelta(hours=6),
                             PAST_WX_STATION if kind == "observed" else NWS_STATION)
        if kind == "forecast" and issued_before is not None:
            rows = [r for r in rows if r["issued_at"] is None or r["issued_at"] <= issued_before]
        pools[kind] = {r["observed_at"]: r for r in rows}
    out, src = [], []
    last = None
    for t in times:
        rec, used = None, "persist"
        for kind in prefer:
            if t in pools[kind]:
                rec, used = pools[kind][t], kind
                break
        if rec is None:
            rec = last
        if rec is None:  # nothing yet: look ahead
            for kind in prefer:
                if pools[kind]:
                    rec = pools[kind][min(pools[kind], key=lambda x: abs((x - t).total_seconds()))]
                    break
        if rec is None:
            raise RuntimeError(f"no weather available around {t}")
        out.append(rec); src.append(used); last = rec
    met = Met(times, [r["wind_ms"] for r in out], [r["wind_dir_deg"] for r in out],
              [r["temp_c"] for r in out], [r["cloud_frac"] for r in out], source="+".join(sorted(set(src))))
    return met, src


def flow_series(times: list[datetime], as_of: datetime) -> tuple[np.ndarray, list[dict], str]:
    """Carry forward the latest gauge value known at as_of, then apply announced flow events (conf >= 0.6)."""
    hist = store.flow_upto(as_of.astimezone(TZ).date(), 1)
    base, src = (float(hist[0]["mgd"]), f"gauge {hist[0]['date']}") if hist else (DEFAULT_FLOW_MGD, "assumed default")
    q = np.full(len(times), base)
    used = []
    for e in store.flow_events():
        if (e.get("confidence") or 0) < 0.6 or e["starts_at"] is None:
            continue
        if e["published_at"] and e["published_at"] > as_of:
            continue  # not known yet at issue time
        end = e["ends_at"] or (e["starts_at"] + timedelta(days=7))
        active = np.array([e["starts_at"] <= t < end for t in times])
        if not active.any():
            continue
        if e.get("expected_flow_mgd") is not None:
            q[active] = e["expected_flow_mgd"]
        elif e.get("flow_delta_mgd") is not None:
            q[active] = np.maximum(q[active] + e["flow_delta_mgd"], 0)
        used.append({"id": e["id"], "event_type": e["event_type"], "quote": e["quote"]})
    return q, used, src


def observations(times: list[datetime]) -> np.ndarray:
    """[H, M] observed ppb at monitors, NaN where missing."""
    idx = {t: i for i, t in enumerate(times)}
    mi = {m.site_id: j for j, m in enumerate(MONITORS)}
    obs = np.full((len(times), len(MONITORS)), np.nan)
    for r in store.readings(times[0], times[-1] + timedelta(hours=1)):
        if r["observed_at"] in idx and r["ppb"] is not None and r["site_id"] in mi:
            obs[idx[r["observed_at"]], mi[r["site_id"]]] = r["ppb"]
    return obs


def load_calibration() -> dict | None:
    if CALIBRATION_PATH.exists():
        return json.loads(CALIBRATION_PATH.read_text())
    return None
