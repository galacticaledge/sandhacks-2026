"""One forecast run: filter -> ensemble -> grids, overlays, receptor series (spec 5.4-5.6).

python -m model.run                      # live run now
python -m model.run --issued 2026-11-13T17:00 --scenario replay --weather observed
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import time
from datetime import datetime, timedelta, timezone

import numpy as np

from config import FORECAST_DIR, MONITORS, ROOT, TZ
from db import store
from model import ensemble, puff
from model.emission import emission_factor
from model.geo import make_grid, to_xy
from model.inputs import assemble_met, flow_series, hours, load_calibration, observations
from model.kalman import LogKFilter, relax_toward
from model.render import write_png
from model.sources import load_sources

log = logging.getLogger("model.run")
UTC = timezone.utc
SPINUP_H = 4
FILTER_H = 48
LEAD_H = 24


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
        src = src.with_params(log_k=cal["log_k"], alpha=cal["alpha"], beta=cal["beta"], shares=np.array(cal["shares"]))
        bg = np.array(cal["background"])
    return src, bg, cal


def run_filter(issued: datetime, src, bg, prior_logk: float, weather_kinds=("observed", "forecast")):
    """Kalman filter on log k over the FILTER_H hours before issue, using data available at issue time."""
    t0 = issued - timedelta(hours=FILTER_H + SPINUP_H)
    times = hours(t0, FILTER_H + SPINUP_H)
    met, _ = assemble_met(times, list(weather_kinds), issued_before=issued)
    flow, _, _ = flow_series(times, issued)
    mx, my = to_xy([m.lat for m in MONITORS], [m.lon for m in MONITORS])
    factor = emission_factor(flow, met.temp_c, src.alpha, src.beta, src.t_ref)
    unit = puff.simulate(met, factor, src, mx, my)  # ppb at monitors for k = 1
    obs = observations(times)
    f = LogKFilter(mean=prior_logk, var=1.0)
    used = 0
    for h in range(SPINUP_H, len(times)):
        f.predict()
        for j in range(len(MONITORS)):
            used += f.update(obs[h, j], float(unit[h, j]), float(bg[j]))
    return f, used


def run_forecast(issued: datetime | None = None, scenario: str = "live", weather: str = "forecast",
                 n_members: int = ensemble.N_MEMBERS, grid: bool = True, cell_m: float | None = None,
                 params=None) -> dict:
    t_start = time.time()
    issued = (issued or datetime.now(TZ)).astimezone(TZ).replace(minute=0, second=0, microsecond=0)
    run_id = issued.astimezone(UTC).strftime("%Y%m%dT%H%MZ") + ("" if scenario == "live" else f"-{scenario}")
    src, bg, cal = params or current_params()

    hist = store.k_history(30) if scenario == "live" else []
    log_k_median = float(np.median(hist)) if len(hist) >= 6 else src.log_k
    f, n_used = run_filter(issued, src, bg, log_k_median)

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
    log_k = relax_toward(f.mean, log_k_median, lead)

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
    p10, p50, p90 = res.p10[sl], res.p50[sl], res.p90[sl]
    valid = times[SPINUP_H:]

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
            "calibration": cal, "members": n_members, "model": "gaussian_puff",
        },
        "receptors": recs, "series": series,
        "elapsed_s": round(time.time() - t_start, 1),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta))
    store.save_run(run_id, scenario, issued, {k: v for k, v in meta["inputs"].items() if k != "met"}, f.mean, f.var, "ok")
    log.info("run %s done in %.1fs (filter used %d obs, log k %.2f±%.2f)", run_id, meta["elapsed_s"], n_used, f.mean, f.var ** .5)
    return meta


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
