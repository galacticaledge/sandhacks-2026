"""Replay, skill."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from config import DEMO_MODE, MONITORS
from db import store
from validate.replay import SKILL_PATH, available_nights, night_hours, replay_night

router = APIRouter(prefix="/api")
UTC = timezone.utc


@router.get("/replay/nights")
def nights():
    out = []
    for d in available_nights():
        nh = night_hours(d)
        obs = store.readings(nh[0], nh[-1] + timedelta(hours=1))
        peaks = {}
        for r in obs:
            if r["ppb"] is not None:
                peaks[r["site_id"]] = max(peaks.get(r["site_id"], -1), r["ppb"])
        out.append({"night": d.isoformat(), "peak_ppb": max(peaks.values()) if peaks else None, "peaks": peaks})
    return out


@router.get("/replay")
async def replay(date_: str | None = None, night: str | None = None):
    """night = the evening date; the forecast was issued at 5 PM that evening, covering 6 PM -> 9 AM."""
    d = night or date_
    try:
        nd = date.fromisoformat(d)
    except (TypeError, ValueError):
        raise HTTPException(400, "night=YYYY-MM-DD required")
    if nd not in available_nights():
        raise HTTPException(404, "no observed data for that night")
    if DEMO_MODE:
        from api.runs import load_meta, valid_run_id
        from validate.replay import replay_run_id
        rid = replay_run_id(nd)
        if not valid_run_id(rid):
            raise HTTPException(404, "night not in demo snapshot")
        meta = load_meta(rid)
    else:
        meta = await run_in_threadpool(replay_night, nd, True)
    nh = night_hours(nd)
    obs_rows = store.readings(meta and datetime.fromisoformat(meta["valid_times"][0]), datetime.fromisoformat(meta["valid_times"][-1]) + timedelta(hours=1))
    observed = {m.site_id: {} for m in MONITORS}
    for r in obs_rows:
        observed[r["site_id"]][r["observed_at"].isoformat()] = r["ppb"]
    return {"night": nd.isoformat(), "run_id": meta["run_id"], "issued_at": meta["issued_at"],
            "valid_times": meta["valid_times"], "night_hours": [t.isoformat() for t in nh],
            "forecast": {m.site_id: meta["series"][m.site_id] for m in MONITORS},
            "observed": {k: [v.get(datetime.fromisoformat(t).astimezone(UTC).isoformat()) for t in meta["valid_times"]] for k, v in observed.items()},
            "inputs": {k: v for k, v in meta["inputs"].items() if k != "calibration"},
            "label": "Replay with observed weather (flatters real forecast skill)"}


@router.get("/skill")
def skill():
    if not SKILL_PATH.exists():
        return {"summary": {}, "nights": [], "note": "no replays scored yet"}
    return json.loads(SKILL_PATH.read_text())
