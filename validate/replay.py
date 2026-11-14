"""Replays (spec 5.7): for each night, issue the 5 PM forecast using only data available then.

Weather comes from the KNRS archive standing in for the forecast, so results are labelled
"with observed weather" -- they flatter real forecast skill.

python -m validate.replay            # replay every available night, then score
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

import numpy as np

from collectors.weather_archive import backfill_weather
from config import DATA_DIR, DEMO_DIR, DEMO_MODE, FORECAST_DIR, MONITORS, TZ
from db import store
from model.geo import make_grid
from model.inputs import observations
from model.run import current_params, run_forecast
from model.sources import load_sources
from validate import baselines, metrics
from validate.calibration_job import fit_window, params_before

log = logging.getLogger("replay")
UTC = timezone.utc
SKILL_PATH = (DEMO_DIR if DEMO_MODE else DATA_DIR) / "skill.json"
REPLAY_MEMBERS = 10


def issue_time(night: date) -> datetime:
    return datetime(night.year, night.month, night.day, 17, tzinfo=TZ)


def night_hours(night: date) -> list[datetime]:
    t0 = datetime(night.year, night.month, night.day, 18, tzinfo=TZ)
    return [(t0 + timedelta(hours=i)).astimezone(UTC) for i in range(15)]


def available_nights() -> list[date]:
    a, b, n = store.reading_range()
    if not a:
        return []
    d, out = (a.astimezone(TZ) - timedelta(days=1)).date(), []
    while d <= b.astimezone(TZ).date():
        obs = observations(night_hours(d))
        if np.isfinite(obs).sum(axis=0).max() >= 6:
            out.append(d)
        d += timedelta(days=1)
    return out


def replay_run_id(night: date) -> str:
    return issue_time(night).astimezone(UTC).strftime("%Y%m%dT%H%MZ") + "-replay"


def replay_night(night: date, grid: bool = False, force: bool = False) -> dict:
    issued = issue_time(night)
    rid = replay_run_id(night)
    meta_path = FORECAST_DIR / rid / "meta.json"
    if meta_path.exists() and not force:
        meta = json.loads(meta_path.read_text())
        if meta.get("grid") or not grid:
            return meta
    backfill_weather(issued - timedelta(days=3), issued + timedelta(days=2))
    params = params_before(issued)
    if params is None:  # not enough history before this night: priors only, never future data
        src = load_sources()
        params = (src, np.full(len(MONITORS), 0.45), {"note": "prior only (not enough history before this night)"})
    return run_forecast(issued, scenario="replay", weather="observed", n_members=REPLAY_MEMBERS, grid=grid, params=params)


def _night_fc(meta: dict, night: date) -> np.ndarray:
    vt = [datetime.fromisoformat(t).astimezone(UTC) for t in meta["valid_times"]]
    idx = [vt.index(t) for t in night_hours(night)]
    return np.array([[meta["series"][m.site_id]["p50"][i] for m in MONITORS] for i in idx])


def leave_one_monitor_out() -> dict:
    a, b, _ = store.reading_range()
    out = {}
    for j, m in enumerate(MONITORS):
        r = fit_window(max(a, b - timedelta(days=120)), b + timedelta(hours=1), mask_monitor=j)
        if not r:
            continue
        res, met, flow, obs, unit = r
        from model.emission import emission_factor
        f = emission_factor(flow, met.temp_c, res.alpha, res.beta)
        others = [k for k in range(len(MONITORS)) if k != j]
        pred = np.exp(res.log_k) * f * np.tensordot(res.shares, unit[:, :, j], axes=(0, 0)) + res.background[others].mean()
        truth = observations(met.times)[:, j]
        ok = np.isfinite(truth)
        if ok.sum() < 12:
            continue
        lp, lt = np.log1p(np.clip(pred[ok], 0, None)), np.log1p(np.clip(truth[ok], 0, None))
        out[m.site_id] = {"mae_log": float(np.mean(np.abs(lp - lt))),
                          "r_log": float(np.corrcoef(lp, lt)[0, 1]) if lt.std() > 0 and lp.std() > 0 else None,
                          "n_hours": int(ok.sum())}
    return out


def spatial_check(run_ids: list[str]) -> dict:
    """Do odor complaints land in the forecast high-concentration area more often than chance?"""
    g = make_grid()
    pct, n = [], 0
    for rid in run_ids:
        d = FORECAST_DIR / rid
        if not (d / "p50.npy").exists():
            continue
        meta = json.loads((d / "meta.json").read_text())
        vt = [datetime.fromisoformat(t).astimezone(UTC) for t in meta["valid_times"]]
        p50 = np.load(d / "p50.npy", mmap_mode="r")
        for c in store.complaints(vt[0], vt[-1] + timedelta(hours=1)):
            ij = g.index_of(c["lat"], c["lon"])
            if ij is None:
                continue
            h = int((c["received_at"].replace(minute=0, second=0) - vt[0]).total_seconds() // 3600)
            if not 0 <= h < len(vt):
                continue
            field = np.asarray(p50[h], dtype=float)
            pct.append(float((field < field[ij]).mean())); n += 1
    if not pct:
        return {"n_complaints": 0}
    top20 = float(np.mean(np.array(pct) >= 0.8))
    return {"n_complaints": n, "mean_percentile": float(np.mean(pct)), "share_in_top20pct_area": top20,
            "chance_share": 0.2}


def score_all() -> dict:
    nights = available_nights()
    per_method = {"model": {}, "persistence": {}, "climatology": {}}
    detail = []
    for night in nights:
        rid = replay_run_id(night)
        if not (FORECAST_DIR / rid / "meta.json").exists():
            continue
        meta = json.loads((FORECAST_DIR / rid / "meta.json").read_text())
        nt = night_hours(night)
        obs = observations(nt)
        fc = {"model": _night_fc(meta, night), "persistence": baselines.persistence(nt),
              "climatology": baselines.climatology(nt, issue_time(night))}
        detail.append({"night": night.isoformat(), "run_id": rid,
                       "obs_peak": {m.site_id: (float(np.nanmax(obs[:, j])) if np.isfinite(obs[:, j]).any() else None) for j, m in enumerate(MONITORS)},
                       "fc_peak": {m.site_id: float(np.nanmax(fc["model"][:, j])) for j, m in enumerate(MONITORS)}})
        for j, m in enumerate(MONITORS):
            # score every method on the same monitor-nights only (fair comparison)
            if min(int((np.isfinite(arr[:, j]) & np.isfinite(obs[:, j])).sum()) for arr in fc.values()) < 6:
                continue
            for meth, arr in fc.items():
                per_method[meth].setdefault(m.site_id, ([], []))
                per_method[meth][m.site_id][0].append(arr[:, j]); per_method[meth][m.site_id][1].append(obs[:, j])
    summary, rows = {}, []
    for meth, sites in per_method.items():
        summary[meth] = {}
        all_scores = []
        for site, (f, o) in sites.items():
            sc = metrics.night_scores(np.array(f), np.array(o))
            all_scores += sc
            summary[meth][site] = metrics.summarize(sc)
        summary[meth]["all"] = metrics.summarize(all_scores)
        for site, s in summary[meth].items():
            for k, v in s.items():
                if v is not None and k != "n_nights":
                    rows.append({"method": meth, "metric": k, "site_id": site, "value": float(v),
                                 "n": s.get("n_nights", 0), "note": "replay, observed weather"})
    store.save_skill(rows)
    a, b, n = store.reading_range()
    result = {"computed_at": datetime.now(UTC).isoformat(), "nights": [d.isoformat() for d in nights],
              "history": {"start": a.isoformat() if a else None, "end": b.isoformat() if b else None, "hours": n},
              "label": "with observed weather (flatters real forecast skill)",
              "summary": summary, "detail": detail, "leave_one_monitor_out": leave_one_monitor_out(),
              "spatial": spatial_check([p.name for p in FORECAST_DIR.glob("*") if (p / "p50.npy").exists()])}
    SKILL_PATH.write_text(json.dumps(result, indent=1))
    return result


def run_all_replays(grid_nights: int = 0, force: bool = False):
    nights = available_nights()
    for i, night in enumerate(nights):
        try:
            replay_night(night, grid=i >= len(nights) - grid_nights, force=force)
        except Exception:
            log.exception("replay %s failed", night)
    return score_all()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    import sys
    r = run_all_replays(grid_nights=3, force='--force' in sys.argv)
    print(json.dumps({k: r[k] for k in ("nights", "history", "summary", "leave_one_monitor_out", "spatial")}, indent=1)[:4000])
