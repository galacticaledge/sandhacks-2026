"""Now, forecast, tonight, events, complaints, receptors."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import os

from alerts.guidance import GUIDANCE
from alerts.rules import evaluate
from api.runs import evening_run_id, latest_run_id, load_meta, point_series, valid_run_id
from config import (DEMO_MODE, FORECAST_DIR, MONITORS, SDAPCD_ALERTS_URL, SDAPCD_GUIDANCE_EN,
                    SDAPCD_GUIDANCE_ES, SDAPCD_H2S_URL, level_for)
from db import store

router = APIRouter(prefix="/api")
UTC = timezone.utc

OFFICIAL = {"sdapcd_h2s": SDAPCD_H2S_URL, "sdapcd_alerts_signup": SDAPCD_ALERTS_URL,
            "guidance_en": SDAPCD_GUIDANCE_EN, "guidance_es": SDAPCD_GUIDANCE_ES}
DISCLAIMER = {"en": "Experimental forecast, not an official advisory. Check SDAPCD for official readings and advisories.",
              "es": "Pronóstico experimental, no es un aviso oficial. Consulte al SDAPCD para lecturas y avisos oficiales."}


def _iso(t):
    return t.isoformat() if t else None


@router.get("/now")
def now():
    latest = {r["site_id"]: r for r in store.latest_readings()}
    monitors = []
    for m in MONITORS:
        r = latest.get(m.site_id)
        monitors.append({"site_id": m.site_id, "name": m.name, "lat": m.lat, "lon": m.lon,
                         "ppb": r["ppb"] if r else None, "level": level_for(max(r["ppb"], 0)) if r and r["ppb"] is not None else None,
                         "observed_at": _iso(r["observed_at"]) if r else None})
    fresh = {k: {kk: (_iso(vv) if isinstance(vv, datetime) else vv) for kk, vv in v.items()}
             for k, v in store.freshness().items()}
    run_id = latest_run_id()
    from model.sources import load_sources
    src = load_sources()
    sources = [{"id": i, "name": n, "lat": float(a), "lon": float(o), "main": k == 0}
               for k, (i, n, a, o) in enumerate(zip(src.ids, src.names, src.lats, src.lons))]
    return {"monitors": monitors, "sources": sources, "latest_run_id": run_id,
            "latest_run_issued_at": load_meta(run_id)["issued_at"] if run_id else None,
            "freshness": fresh, "demo_mode": DEMO_MODE, "official": OFFICIAL, "disclaimer": DISCLAIMER,
            "credits": ["UCSD Resilient Shield", "San Diego County Air Pollution Control District (SDAPCD)"]}


def _resolve(run_id: str) -> str:
    rid = latest_run_id() if run_id == "latest" else run_id
    if not rid or not valid_run_id(rid):
        raise HTTPException(404, "run not found")
    return rid


@router.get("/forecast/{run_id}/meta")
def forecast_meta(run_id: str):
    m = dict(load_meta(_resolve(run_id)))
    return m


@router.get("/forecast/{run_id}/grid/{hour}.png")
def grid_png(run_id: str, hour: int, pct: str = Query("p50", pattern="^p(50|90)$")):
    rid = _resolve(run_id)
    if not 0 <= hour < 24:
        raise HTTPException(404)
    path = FORECAST_DIR / rid / "png" / f"{pct}_{hour:02d}.png"
    if not path.exists():
        raise HTTPException(404)
    bounds = load_meta(rid)["grid"]["bounds"]
    return FileResponse(path, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400", "X-Bounds": str(bounds)})


@router.get("/forecast/{run_id}/point")
def point(run_id: str, lat: float, lon: float):
    rid = _resolve(run_id)
    s = point_series(rid, lat, lon)
    if s is None:
        raise HTTPException(400, "point is outside the forecast area")
    meta = load_meta(rid)
    return {"run_id": rid, "issued_at": meta["issued_at"], "valid_times": meta["valid_times"], "lat": lat, "lon": lon,
            **s, "levels": [level_for(v) for v in s["p50"]], "disclaimer": DISCLAIMER}


@router.get("/tonight")
def tonight(lang: str = Query("en", pattern="^(en|es)$")):
    rid, which = evening_run_id()
    if not rid:
        raise HTTPException(503, "no forecast run yet")
    meta = load_meta(rid)
    vt = [datetime.fromisoformat(t) for t in meta["valid_times"]]
    items = []
    for r in meta["receptors"]:
        s = meta["series"][r["id"]]
        ev = evaluate(vt, s["p10"], s["p50"], s["p90"])
        lvl = ev.get("level") or "green"
        ev = {("alert" if k == "kind" else k): v for k, v in ev.items()}
        items.append({**r, **ev, "guidance": GUIDANCE[lang][lvl]})
    items.sort(key=lambda x: -(x.get("peak_p50") or 0))
    return {"run_id": rid, "run_kind": which, "issued_at": meta["issued_at"], "items": items,
            "disclaimer": DISCLAIMER[lang], "official": OFFICIAL}


@router.get("/receptors")
def receptors():
    from model.run import receptors as recs
    return recs()


@router.get("/complaints")
def complaints(days: int = Query(7, ge=1, le=365)):
    end = datetime.now(UTC)
    rows = store.complaints(end - timedelta(days=days), end)
    return [{"lat": r["lat"], "lon": r["lon"], "received_at": _iso(r["received_at"]), "nature": r["nature"]} for r in rows]


@router.get("/spills")
def spills():
    return store.query("SELECT * FROM spills")


@router.get("/events")
def events():
    return [{**e, **{k: _iso(e[k]) for k in ("published_at", "starts_at", "ends_at")},
             "used_in_model": (e.get("confidence") or 0) >= 0.6} for e in store.flow_events()]


class ManualEvent(BaseModel):
    event_type: str = Field(pattern="^(pump_shutdown|collector_failure|repair|diversion|storm|other)$")
    location_text: str = ""
    starts_at: datetime
    ends_at: datetime | None = None
    expected_flow_mgd: float | None = None
    flow_delta_mgd: float | None = None
    peak_flow_mgd: float | None = None
    confidence: float = Field(1.0, ge=0, le=1)
    quote: str
    source_url: str = ""


@router.post("/admin/events")
def add_event(e: ManualEvent, x_admin_token: str = Header("")):
    """Fallback when Gemini is down: hand-entered flow events (spec 6)."""
    token = os.getenv("ADMIN_TOKEN")
    if not token or x_admin_token != token:
        raise HTTPException(403, "admin token required")
    import uuid
    store.upsert_flow_event({**e.model_dump(), "id": "manual-" + uuid.uuid4().hex[:10],
                             "published_at": datetime.now(UTC), "entered_by": "admin"})
    return {"ok": True}
