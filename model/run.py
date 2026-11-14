"""One forecast run: filter -> ensemble physics -> monitor correction -> grids, overlays, receptor series.

Physics (spec 5.2-5.6): puff model, Kalman filter on log k, 20-member ensemble; its pointwise median is
the physics field. Correction (model/blend.py): tonight's peak at each monitor is predicted from that
physics peak plus the monitor's own recent readings; P10/P50/P90 come from the correction's past errors
and are spread over the grid, so the map and the monitor forecasts agree.

python -m model.run                      # live run now
python -m model.run --issued 2026-11-13T17:00 --scenario replay --weather observed
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import time
from datetime import date, datetime, timedelta, timezone

import numpy as np

from config import FORECAST_DIR, MONITORS, ROOT, TZ
from db import store
from model import blend, ensemble, kalman, puff
from model.geo import make_grid, to_xy
from model.inputs import assemble_met, flow_series, hours, load_calibration, observations
from model.kalman import RELAX_TAU_H, LogKFilter, relax_toward
from model.render import write_png
from model.sources import load_sources

log = logging.getLogger("model.run")
UTC = timezone.utc
SPINUP_H = 4
FILTER_H = 240   # the filter forgets within a few days; ten covers it
LEAD_H = 24
MAX_PPB = 2000.0


def receptors() -> list[dict]:
    fc = json.loads((ROOT / "data" / "receptors.geojson").read_text())
    out = [{"id": f["properties"]["id"], "name": f["properties"]["name"], "kind": f["properties"]["kind"],
            "lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1]} for f in fc["features"]]
    out += [{"id": m.site_id, "name": m.name, "kind": "monitor", "lat": m.lat, "lon": m.lon} for m in MONITORS]
    return out


def current_params():
    src = load_sources()
    cal = load_calibration()
    bg = np.full(len(MONITORS), 0.45)
    if cal:
        src = src.with_params(log_k=cal["log_k"], alpha=cal["alpha"], beta=cal["beta"], shares=np.array(cal["shares"]),
                              q_dil=cal.get("q_dil_mgd", 0.0), dil_gamma=cal.get("dil_gamma", 2.0),
                              sigma_v=cal.get("sigma_v_ms", src.sigma_v))
        bg = np.array(cal["background"])
    return src, bg, cal


def run_filter(issued: datetime, src, bg, weather_kinds=("observed", "forecast")):
    """Kalman filter on log k over the FILTER_H hours before issue, using data available at issue time.
    Starts from the calibrated base k; an hour counts only when the base model puts signal on the monitor."""
    t0 = issued - timedelta(hours=FILTER_H + SPINUP_H)
    times = hours(t0, FILTER_H + SPINUP_H)
    met, _ = assemble_met(times, list(weather_kinds), issued_before=issued)
    flow, _, _ = flow_series(times, issued)
    mx, my = monitor_xy()
    unit = np.tensordot(src.shares, puff.simulate_points(met, np.ones(len(met)), src, mx, my), axes=(0, 0))
    unit = unit * src.factor(flow, met.temp_c)[:, None]   # ppb at monitors for k = 1
    obs = observations(times)
    obs[:SPINUP_H] = np.nan
    means, variances, used = kalman.run_series(obs, unit, bg, src.log_k)
    return LogKFilter(mean=float(means[-1]), var=float(variances[-1]), ref=src.log_k), used


def monitor_xy():
    return to_xy([m.lat for m in MONITORS], [m.lon for m in MONITORS])


def last_complete_night(issued: datetime) -> date:
    """Evening date of the most recent 6 PM - 9 AM night that had ended by the issue time."""
    loc = issued.astimezone(TZ)
    return loc.date() - timedelta(days=1 if loc.hour >= blend.NIGHT_END_H else 2)


def history_inputs(issued: datetime, base: np.ndarray) -> dict[str, np.ndarray]:
    """The correction's history features from readings before the issue hour only."""
    last = last_complete_night(issued)
    prev = np.full((blend.WEEK_N, len(MONITORS)), np.nan)
    for b in range(blend.WEEK_N):
        d = last - timedelta(days=b)
        prev[b] = blend.night_peak(observations(hours(datetime(d.year, d.month, d.day, blend.NIGHT_START_H, tzinfo=TZ), 15)))
    today = observations(hours(issued - timedelta(hours=blend.TODAY_H), blend.TODAY_H))
    return blend.history_features(prev, today, base)


def correct(issued: datetime, valid: list[datetime], physics_mon: np.ndarray, cal_blend: dict) -> dict | None:
    """Night-peak quantiles and scale factors at the monitors. physics_mon [hours, M] over `valid`."""
    night = [i for i, t in enumerate(valid) if blend.is_night_hour(t.astimezone(TZ).hour)]
    if not night:
        return None
    peak = physics_mon[night].max(axis=0)
    feats = history_inputs(issued, np.asarray(cal_blend["base"], dtype=float))
    X = blend.design(peak, feats)
    q = blend.predict(cal_blend, X)
    return {"quantiles": q, "scale": blend.scales(q, peak), "physics_peak": peak, "features": feats,
            "night": np.array([i in night for i in range(len(valid))]),
            "mult": blend.multipliers(blend.scales(q, peak), cal_blend.get("hourly_ratio")),
            "contributions": blend.contributions(cal_blend, X)}


def run_forecast(issued: datetime | None = None, scenario: str = "live", weather: str = "forecast",
                 n_members: int = ensemble.N_MEMBERS, grid: bool = True, cell_m: float | None = None,
                 params=None) -> dict:
    t_start = time.time()
    issued = (issued or datetime.now(TZ)).astimezone(TZ).replace(minute=0, second=0, microsecond=0)
    run_id = issued.astimezone(UTC).strftime("%Y%m%dT%H%MZ") + ("" if scenario == "live" else f"-{scenario}")
    src, bg, cal = params or current_params()

    log_k_median = src.log_k   # calibrated base; the filter state is held through the forecast (RELAX_TAU_H)
    f, n_used = run_filter(issued, src, bg)

    times = hours(issued - timedelta(hours=SPINUP_H), SPINUP_H + LEAD_H)
    if weather == "observed":
        met, met_src = assemble_met(times, ["observed"])
    else:
        met, met_src = assemble_met(times, ["forecast", "observed"],
                                    issued_before=issued + timedelta(minutes=59))
        # spin-up hours are in the past: prefer what was observed
        spin, spin_src = assemble_met(times[:SPINUP_H], ["observed", "forecast"])
        met.wind_ms[:SPINUP_H] = spin.wind_ms; met.wind_dir_deg[:SPINUP_H] = spin.wind_dir_deg
        met.temp_c[:SPINUP_H] = spin.temp_c; met.cloud_frac[:SPINUP_H] = spin.cloud_frac
        met.stab[:SPINUP_H] = spin.stab; met_src[:SPINUP_H] = spin_src
    flow, events_used, flow_src = flow_series(times, issued)
    lead = np.array([max(i - SPINUP_H, 0) for i in range(len(times))])
    log_k = relax_toward(f.mean, log_k_median, lead, RELAX_TAU_H)

    recs = receptors()
    rx, ry = to_xy([r["lat"] for r in recs], [r["lon"] for r in recs])
    g = (make_grid(cell_m) if cell_m else make_grid()) if grid else None
    if g is not None:
        ax = np.concatenate([g.x, rx.astype(np.float32)]); ay = np.concatenate([g.y, ry.astype(np.float32)])
    else:
        ax, ay = rx, ry
    bg_mean = float(np.mean(bg))
    bgv = np.full(len(ax), bg_mean, dtype=np.float32)
    for j, m in enumerate(MONITORS):  # monitor receptors get their own fitted background
        bgv[len(ax) - len(MONITORS) + j] = bg[j]
    res = ensemble.run(met, flow, log_k, f.var, src, ax, ay, bgv, n=n_members)
    sl = slice(SPINUP_H, None)
    valid = times[SPINUP_H:]
    nm = len(MONITORS)
    physics = res.p50[sl]
    corr = correct(issued, valid, physics[:, -nm:], cal["blend"]) if cal and cal.get("blend") else None
    if corr is not None:
        # multipliers are interpolated between monitors, so the map matches the monitor forecasts
        mx, my = monitor_xy()
        mult = blend.spread_scales(corr["mult"], mx, my, ax, ay)
        mult[-nm:] = corr["mult"]
        p10, p50, p90 = blend.hourly_quantiles(physics, corr["night"], mult)
    else:   # no correction fitted: raw ensemble percentiles
        p10, p50, p90 = res.p10[sl], physics, res.p90[sl]
    # a point source is not valid within ~100 m of the river: cap the map there (highest reading on record: 915 ppb)
    p10, p50, p90 = (np.minimum(a, MAX_PPB) for a in (p10, p50, p90))

    out_dir = FORECAST_DIR / run_id
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    ng = 0
    if g is not None:
        ng = g.x.size
        shape = (LEAD_H,) + g.shape
        for name, arr in (("p10", p10), ("p50", p50), ("p90", p90)):
            np.save(out_dir / f"{name}.npy", arr[:, :ng].reshape(shape).astype(np.float16))
        (out_dir / "png").mkdir()
        for h in range(LEAD_H):
            write_png(p50[h, :ng].reshape(g.shape), out_dir / "png" / f"p50_{h:02d}.png")
            write_png(p90[h, :ng].reshape(g.shape), out_dir / "png" / f"p90_{h:02d}.png")

    rows, series = [], {}
    for k, r in enumerate(recs):
        c = ng + k
        series[r["id"]] = {k: [round(float(v), 2) for v in arr[:, c]] for k, arr in (("p10", p10), ("p50", p50), ("p90", p90))}
        for h, t in enumerate(valid):
            rows.append({"scenario": scenario, "issued_at": issued, "valid_at": t, "receptor_id": r["id"],
                         "p10": float(p10[h, c]), "p50": float(p50[h, c]), "p90": float(p90[h, c]), "run_id": run_id})
    store.upsert_receptor_forecasts(rows)

    meta = {
        "run_id": run_id, "scenario": scenario, "issued_at": issued.isoformat(),
        "valid_times": [t.isoformat() for t in valid],
        "grid": {"bounds": g.bounds, "shape": list(g.shape), "cell_m": cell_m or 50} if g is not None else None,
        "inputs": {
            "met": met.slice(SPINUP_H, len(times)).to_dict(),
            "met_hour_sources": met_src[SPINUP_H:],
            "flow_mgd": np.round(flow[SPINUP_H:], 1).tolist(), "flow_source": flow_src, "flow_events": events_used,
            "log_k_now": f.mean, "log_k_var": f.var, "log_k_median_30d": log_k_median,
            "log_k_series": np.round(log_k[SPINUP_H:], 3).tolist(), "filter_obs_used": n_used,
            "alpha": src.alpha, "beta": src.beta, "shares": dict(zip(src.ids, np.round(src.shares, 3).tolist())),
            "background_ppb": dict(zip([m.site_id for m in MONITORS], np.round(bg, 2).tolist())),
            "calibration": cal, "members": n_members,
            "model": "gaussian_puff+monitor_correction" if corr is not None else "gaussian_puff",
            "sigma_v_ms": src.sigma_v, "q_dil_mgd": src.q_dil, "log_k_base": src.log_k,
            "correction": correction_meta(corr, cal),
        },
        "receptors": recs, "series": series,
        "elapsed_s": round(time.time() - t_start, 1),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta))
    store.save_run(run_id, scenario, issued, {k: v for k, v in meta["inputs"].items() if k != "met"}, f.mean, f.var, "ok")
    log.info("run %s done in %.1fs (filter used %d obs, log k %.2f±%.2f)", run_id, meta["elapsed_s"], n_used, f.mean, f.var ** .5)
    return meta


def correction_meta(corr: dict | None, cal: dict | None) -> dict | None:
    """What the monitor correction did, per monitor, so the forecast shows its inputs."""
    if corr is None:
        return None
    ids = [m.site_id for m in MONITORS]
    r = lambda v: round(float(v), 3)
    return {
        "note": "night peak = physics peak corrected by the monitor's own recent readings; "
                "P10/P90 from the correction's past errors",
        "fit_before": cal["blend"].get("fit_before"),
        "physics_peak_ppb": {s: r(corr["physics_peak"][j]) for j, s in enumerate(ids)},
        "night_peak_ppb": {s: dict(zip(("p10", "p50", "p90"), map(r, corr["quantiles"][j]))) for j, s in enumerate(ids)},
        "scale": {s: dict(zip(("p10", "p50", "p90"), map(r, corr["scale"][j]))) for j, s in enumerate(ids)},
        "features_log1p_ppb": {s: {k: r(v[j]) for k, v in corr["features"].items()} for j, s in enumerate(ids)},
        "contributions_log1p": {s: {k: r(v) for k, v in corr["contributions"][j].items()} for j, s in enumerate(ids)},
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--issued"); ap.add_argument("--scenario", default="live")
    ap.add_argument("--weather", default="forecast"); ap.add_argument("--members", type=int, default=ensemble.N_MEMBERS)
    a = ap.parse_args()
    issued = datetime.fromisoformat(a.issued).replace(tzinfo=TZ) if a.issued else None
    m = run_forecast(issued, a.scenario, a.weather, a.members)
    s = m["series"]
    for rid in ("nestor_bes", "ib_civic", "san_ysidro", "nb_nestor"):
        print(rid, "peak p50 %.1f p90 %.1f" % (max(s[rid]["p50"]), max(s[rid]["p90"])))
    print("elapsed", m["elapsed_s"], "s")
