"""Replays (spec 5.7): for each night, issue the 5 PM forecast using only data available then.

Weather comes from the KNRS archive standing in for the forecast, so results are labelled
"with observed weather" -- they flatter real forecast skill.

The calibration (data/calibration.json) is fitted once on nights before hindcast.TUNE_END and frozen,
so nights from TUNE_END on are a held-out test; scores are reported for both periods.

python -m validate.replay            # replay every available night (grids for GRID_NIGHTS + last 3), then score
python -m validate.replay --force    # recompute nights that already have a folder
python -m validate.replay --score    # only rescore existing replays
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
from model import ensemble
from model.run import current_params, run_forecast
from validate import baselines, metrics
from validate import hindcast

log = logging.getLogger("replay")
UTC = timezone.utc
SKILL_PATH = (DEMO_DIR if DEMO_MODE else DATA_DIR) / "skill.json"
REPLAY_MEMBERS = ensemble.N_MEMBERS   # same ensemble as the live run
# spike nights the demo shows on the map (evening dates)
GRID_NIGHTS = [date(2026, 3, 29), date(2026, 4, 19), date(2026, 4, 4), date(2025, 2, 23)]


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


def replay_night(night: date, grid: bool = False, force: bool = False, params=None) -> dict:
    issued = issue_time(night)
    rid = replay_run_id(night)
    meta_path = FORECAST_DIR / rid / "meta.json"
    if meta_path.exists() and not force:
        meta = json.loads(meta_path.read_text())
        if meta.get("grid") or not grid:
            return meta
    backfill_weather(issued - timedelta(days=3), issued + timedelta(days=2))
    return run_forecast(issued, scenario="replay", weather="observed", n_members=REPLAY_MEMBERS, grid=grid,
                        params=params or current_params())


def _night_fc(meta: dict, night: date, q: str = "p50") -> np.ndarray:
    vt = [datetime.fromisoformat(t).astimezone(UTC) for t in meta["valid_times"]]
    idx = [vt.index(t) for t in night_hours(night)]
    return np.array([[meta["series"][m.site_id][q][i] for m in MONITORS] for i in idx])


def leave_one_monitor_out() -> dict:
    """Refit everything (physics, filter, correction) without one monitor's readings, then forecast that
    monitor like any street point: mean background, correction interpolated from the other two.
    Fitted on nights before TUNE_END; scored on the held-out nights. Uses the fast hindcast."""
    out = {}
    for j, m in enumerate(MONITORS):
        hc, _ = hindcast.calibrate_all(hindcast.TUNE_END, mask_monitor=j)
        hist = hc.hist
        obs = hist.obs[hist.night_idx]
        r = metrics.evaluate(obs, {"model": hc.p[1], **hindcast.baseline_arrays(hist)}, hindcast.blend_mod_prev_peak(hist),
                             [x.site_id for x in MONITORS], ~hist.tune, {"model_possible": hc.p[2]})
        e = r["eligible"][:, j]
        ok = np.isfinite(obs[:, :, j]) & e[:, None]
        lp, lt = np.log1p(hc.p[1][:, :, j][ok]), np.log1p(np.clip(obs[:, :, j][ok], 0, None))
        peak_obs = np.where(np.isfinite(obs[:, :, j]), obs[:, :, j], -np.inf).max(axis=1)[e]
        out[m.site_id] = {"mae_log": float(np.mean(np.abs(lp - lt))),
                          "r_log": float(np.corrcoef(lp, lt)[0, 1]) if lt.std() > 0 and lp.std() > 0 else None,
                          "n_hours": int(ok.sum()), "n_nights": int(e.sum()), "period": "held_out",
                          "binary": r["binary"]["all_nights"][m.site_id],
                          "auc_p50_peak": metrics.auc(hc.quantiles[e, j, 1], peak_obs >= metrics.ORANGE_PPB),
                          "night_peak_under_p90": float((peak_obs <= hc.quantiles[e, j, 2]).mean()) if e.any() else None}
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


def _period_scores(obs, fc, p90, prev, sel, sites) -> dict:
    r = metrics.evaluate(obs, fc, prev, sites, sel, {"model_possible": p90})
    e = r["eligible"]
    _, fp, op, _ = metrics._peaks(fc["model"], obs)
    ranking = {}
    for s_id, cols in [(s, np.arange(len(sites)) == j) for j, s in enumerate(sites)] + [("all", np.ones(len(sites), bool))]:
        m = e & cols[None, :]
        if not m.any():
            continue
        ev = op[m] >= metrics.ORANGE_PPB
        row = {"n": int(m.sum())}
        for meth, arr in fc.items():
            row[f"auc_{meth}"] = metrics.auc(metrics._peaks(arr, obs)[1][m], ev)
        # the model's hit rate if it raised exactly as many alarms as persistence did
        n_alarm = int((metrics._peaks(fc["persistence"], obs)[1][m] >= metrics.ORANGE_PPB).sum())
        if n_alarm and ev.any():
            top = np.argsort(-fp[m], kind="stable")[:n_alarm]
            row["alarms_matched_to_persistence"] = n_alarm
            row["model_hit_rate_at_persistence_alarm_count"] = float(ev[top].sum() / ev.sum())
            row["model_false_alarm_ratio_at_persistence_alarm_count"] = float((~ev[top]).sum() / n_alarm)
        ranking[s_id] = row
    return {"summary": r["summary"], "binary": r["binary"], "coverage": metrics.coverage(obs, p90, e), "ranking": ranking,
            "eligible": e}


def score_all() -> dict:
    nights = available_nights()
    sites = [m.site_id for m in MONITORS]
    scored, rows_obs, rows_fc, rows_p90, rows_prev, detail = [], [], {"model": [], "persistence": [], "climatology": []}, [], [], []
    for night in nights:
        rid = replay_run_id(night)
        if not (FORECAST_DIR / rid / "meta.json").exists():
            continue
        meta = json.loads((FORECAST_DIR / rid / "meta.json").read_text())
        nt = night_hours(night)
        obs = observations(nt)
        pers = baselines.persistence(nt)
        scored.append(night); rows_obs.append(obs)
        rows_fc["model"].append(_night_fc(meta, night)); rows_fc["persistence"].append(pers)
        rows_fc["climatology"].append(baselines.climatology(nt, issue_time(night)))
        p90 = _night_fc(meta, night, "p90")
        rows_p90.append(p90)
        from model.blend import night_peak
        rows_prev.append(night_peak(pers))
        detail.append({"night": night.isoformat(), "run_id": rid,
                       "obs_peak": {m.site_id: (float(np.nanmax(obs[:, j])) if np.isfinite(obs[:, j]).any() else None) for j, m in enumerate(MONITORS)},
                       "fc_peak": {m.site_id: float(np.nanmax(rows_fc["model"][-1][:, j])) for j, m in enumerate(MONITORS)},
                       "fc_peak_p90": {m.site_id: float(np.nanmax(p90[:, j])) for j, m in enumerate(MONITORS)}})
    a, b, n = store.reading_range()
    result = {"computed_at": datetime.now(UTC).isoformat(), "nights": [d.isoformat() for d in nights],
              "history": {"start": a.isoformat() if a else None, "end": b.isoformat() if b else None, "hours": n},
              "label": "with observed weather (flatters real forecast skill)", "summary": {}, "detail": detail}
    if scored:
        obs = np.array(rows_obs); fc = {k: np.array(v) for k, v in rows_fc.items()}
        p90 = np.array(rows_p90); prev = np.array(rows_prev)
        tune = np.array([d < hindcast.TUNE_END for d in scored])
        periods = {"all": _period_scores(obs, fc, p90, prev, None, sites),
                   "tuning": _period_scores(obs, fc, p90, prev, tune, sites),
                   "held_out": _period_scores(obs, fc, p90, prev, ~tune, sites)}
        result["summary"] = periods["all"]["summary"]
        rows = []
        for meth, by_site in result["summary"].items():
            for site, sc in by_site.items():
                rows += [{"method": meth, "metric": k, "site_id": site, "value": float(v), "n": sc.get("n_nights", 0),
                          "note": "replay, observed weather"} for k, v in sc.items() if v is not None and k != "n_nights"]
        store.save_skill(rows)
        result["summary_by_period"] = {k: v["summary"] for k, v in periods.items()}
        result["binary"] = {
            "threshold_ppb": metrics.ORANGE_PPB,
            "rules": {"model_likely": "forecast P50 reaches 30 ppb in the 6 PM-9 AM window",
                      "model_possible": "forecast P90 reaches 30 ppb (includes every likely night)",
                      "persistence": "last night reached 30 ppb", "climatology": "30-day hour-of-day mean reaches 30 ppb"},
            "split": {"tuning": "nights before %s (model fitted here: in-sample)" % hindcast.TUNE_END.isoformat(),
                      "held_out": "nights from %s on (never used to fit or choose the model)" % hindcast.TUNE_END.isoformat()},
            "subsets": {"all_nights": "every scored monitor-night",
                        "after_quiet_night": "monitor-nights whose previous night stayed under 30 ppb (persistence cannot hit these)"},
            "periods": {k: v["binary"] for k, v in periods.items()}}
        result["coverage"] = {k: v["coverage"] for k, v in periods.items()}
        result["ranking"] = {k: v["ranking"] for k, v in periods.items()}
    cal = current_params()[2] or {}
    result["model"] = {"description": "Gaussian puff physics (meander, storm-water dilution, Kalman filter on emission) "
                                      "corrected by the monitors' own recent readings",
                       "calibration_fit_before": cal.get("fit_before"), "members": REPLAY_MEMBERS,
                       "physics": {k: cal.get(k) for k in ("log_k", "alpha", "beta", "shares", "background", "q_dil_mgd", "dil_gamma", "sigma_v_ms")},
                       "correction": cal.get("blend")}
    result["leave_one_monitor_out"] = leave_one_monitor_out()
    result["spatial"] = {"n_complaints": 0, "note": "not computed: most complaint records share one coordinate"}
    SKILL_PATH.write_text(json.dumps(result, indent=1))
    return result


def run_all_replays(grid_nights: int = 0, force: bool = False):
    nights = available_nights()
    params = current_params()
    want_grid = set(nights[len(nights) - grid_nights:] if grid_nights else []) | set(GRID_NIGHTS)
    for i, night in enumerate(nights):
        try:
            replay_night(night, grid=night in want_grid, force=force, params=params)
        except Exception:
            log.exception("replay %s failed", night)
        if i % 100 == 0:
            log.info("replayed %d / %d nights", i + 1, len(nights))
    return score_all()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    import sys
    r = score_all() if "--score" in sys.argv else run_all_replays(grid_nights=3, force="--force" in sys.argv)
    print(json.dumps({k: r.get(k) for k in ("history", "summary_by_period", "coverage", "ranking", "leave_one_monitor_out")}, indent=1)[:6000])
