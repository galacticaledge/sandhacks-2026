"""Replay, skill."""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from alerts.rules import night_window
from api.runs import load_meta, valid_run_id
from config import DATA_DIR, DEMO_DIR, DEMO_MODE, FORECAST_DIR, MONITORS, TZ
from db import store
from validate.replay import SKILL_PATH, night_hours, replay_night, replay_run_id

router = APIRouter(prefix="/api")
UTC = timezone.utc


def _featured() -> dict:
    """Optional {"night": "YYYY-MM-DD", "receptor_id": "..."} that the demo should open on."""
    p = (DEMO_DIR if DEMO_MODE else DATA_DIR) / "featured_night.json"
    try:
        j = json.loads(p.read_text())
        return {"night": date.fromisoformat(j["night"]).isoformat(), "receptor_id": j.get("receptor_id")}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def _seeded_nights() -> set[str]:
    """Nights the seed picked (scripts/seed.py, scripts/make_demo.py write them next to the featured night).
    When present, the Replay list shows only these; REPLAY_LIST=all shows every night with readings."""
    if os.getenv("REPLAY_LIST", "seeded").strip().lower() == "all":
        return set()
    p = (DEMO_DIR if DEMO_MODE else DATA_DIR) / "featured_night.json"
    try:
        return {date.fromisoformat(d).isoformat() for d in json.loads(p.read_text()).get("nights", [])}
    except (OSError, ValueError, TypeError, AttributeError):
        return set()


def _night_stats() -> dict[date, dict[str, float]]:
    """One query: every night with >= 6 hourly readings at some monitor -> that night's peak per monitor.
    A night is the evening date; it covers 6 PM that day to 8 AM the next (same hours as validate.replay.night_hours)."""
    rows = store.query("SELECT observed_at, site_id, ppb FROM h2s_readings WHERE ppb IS NOT NULL")
    count: dict[tuple[date, str], int] = {}
    peak: dict[tuple[date, str], float] = {}
    for r in rows:
        t = store.dt(r["observed_at"]).astimezone(TZ)
        if t.hour >= 18:
            d = t.date()
        elif t.hour <= 8:
            d = t.date() - timedelta(days=1)
        else:
            continue
        k = (d, r["site_id"])
        count[k] = count.get(k, 0) + 1
        peak[k] = max(peak.get(k, -1e9), r["ppb"])
    out: dict[date, dict[str, float]] = {}
    for (d, site), n in count.items():
        out.setdefault(d, {})[site] = peak[(d, site)]
    return {d: p for d, p in out.items() if any(count[(d, s)] >= 6 for s in p)}


def _has_grid(nd: date) -> bool:
    return (FORECAST_DIR / replay_run_id(nd) / "p50.npy").exists()


@router.get("/replay/nights")
def nights():
    """Newest first. Each night: observed peak, whether a map grid exists, and `featured` (one night at most)."""
    stats = _night_stats()
    seeded = _seeded_nights()
    days = sorted((d for d in stats if (not DEMO_MODE or valid_run_id(replay_run_id(d)))
                   and (not seeded or d.isoformat() in seeded)), reverse=True)
    feat = _featured()
    fnight = feat.get("night") if feat.get("night") in {d.isoformat() for d in days} else None
    if not fnight:
        fnight = next((d.isoformat() for d in days if _has_grid(d)), None)
    out = []
    for d in days:
        peaks = {k: round(v, 1) for k, v in stats[d].items()}
        f = d.isoformat() == fnight
        out.append({"night": d.isoformat(), "peak_ppb": max(peaks.values()) if peaks else None, "peaks": peaks,
                    "has_grid": _has_grid(d), "featured": f, "receptor_id": feat.get("receptor_id") if f else None})
    return out


def _night_meta(nd: date) -> dict:
    """The replay run for this night: from disk if it exists, else (live mode only) computed without a grid."""
    if nd not in _night_stats():
        raise HTTPException(404, "no observed data for that night")
    rid = replay_run_id(nd)
    if valid_run_id(rid):
        return load_meta(rid)
    if DEMO_MODE:
        raise HTTPException(404, "night not in demo snapshot")
    return replay_night(nd, False)


def _parse_night(d: str | None) -> date:
    try:
        return date.fromisoformat(d)
    except (TypeError, ValueError):
        raise HTTPException(400, "date=YYYY-MM-DD required")


def _default_receptor(meta: dict) -> str | None:
    """Neighborhood or school with the highest forecast median peak that night (the alert preview opens on it)."""
    w = night_window([datetime.fromisoformat(t).astimezone(TZ) for t in meta["valid_times"]])
    best, bid = -1.0, None
    for r in meta["receptors"]:
        if r["kind"] == "monitor" or r["id"] not in meta["series"]:
            continue
        peak = max((meta["series"][r["id"]]["p50"][i] for i in w), default=-1.0)
        if peak > best:
            best, bid = peak, r["id"]
    return bid


@router.get("/replay")
async def replay(date_: str | None = Query(None, alias="date"), night: str | None = None):
    """date (or night) = the evening date; the forecast was issued at 5 PM that evening, covering 6 PM -> 9 AM."""
    nd = _parse_night(night or date_)
    meta = await run_in_threadpool(_night_meta, nd)
    nh = night_hours(nd)
    obs_rows = store.readings(datetime.fromisoformat(meta["valid_times"][0]), datetime.fromisoformat(meta["valid_times"][-1]) + timedelta(hours=1))
    observed = {m.site_id: {} for m in MONITORS}
    for r in obs_rows:
        observed[r["site_id"]][r["observed_at"].isoformat()] = r["ppb"]
    feat = _featured()
    return {"night": nd.isoformat(), "run_id": meta["run_id"], "issued_at": meta["issued_at"],
            "valid_times": meta["valid_times"], "night_hours": [t.isoformat() for t in nh],
            "has_grid": bool(meta.get("grid")),
            "forecast": {m.site_id: meta["series"][m.site_id] for m in MONITORS},
            "observed": {k: [v.get(datetime.fromisoformat(t).astimezone(UTC).isoformat()) for t in meta["valid_times"]] for k, v in observed.items()},
            "inputs": {k: v for k, v in meta["inputs"].items() if k != "calibration"},
            "default_receptor_id": feat["receptor_id"] if feat.get("night") == nd.isoformat() and feat.get("receptor_id") else _default_receptor(meta),
            "label": "Replay with observed weather (flatters real forecast skill)"}


@router.get("/replay/alert")
async def replay_alert(night: str, receptor_id: str, lang: str = Query("en", pattern="^(en|es)$")):
    """The email the 5:15 PM alert job would have sent for this place on this night, or {kind: none}."""
    from alerts.rules import evaluate
    from alerts.send import render
    nd = _parse_night(night)
    meta = await run_in_threadpool(_night_meta, nd)
    rec = next((r for r in meta["receptors"] if r["id"] == receptor_id), None)
    if not rec or receptor_id not in meta["series"]:
        raise HTTPException(404, "unknown receptor")
    s = meta["series"][receptor_id]
    ev = evaluate([datetime.fromisoformat(t).astimezone(TZ) for t in meta["valid_times"]], s["p10"], s["p50"], s["p90"])
    if ev["kind"] not in ("likely", "possible"):
        return {"kind": "none", "receptor_id": receptor_id, "place": rec["name"]}
    subject, body = render(lang, rec["name"], ev, "/api/unsubscribe/preview-only")
    would = datetime(nd.year, nd.month, nd.day, 17, 15, tzinfo=TZ)
    return {"kind": ev["kind"], "receptor_id": receptor_id, "place": rec["name"], "subject": subject, "body": body,
            "would_send_at": would.isoformat(), "peak_p50": ev["peak_p50"], "peak_p90": ev["peak_p90"]}


@router.get("/skill")
def skill():
    if not SKILL_PATH.exists():
        return {"summary": {}, "nights": [], "note": "no replays scored yet"}
    return json.loads(SKILL_PATH.read_text())
