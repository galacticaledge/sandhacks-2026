"""Fast hindcast: the 5 PM forecast at the monitors for every night of the history, in seconds.

It runs the same steps as model.run (puff physics -> Kalman filter on log k -> ensemble median ->
monitor correction) but only at the monitors, with the puff responses for the whole history computed
once per ensemble member and cached. Used to fit the calibration (physics + correction), for the
leave-one-monitor-out test and for quick experiments. The published scores come from the real
pipeline (validate.replay); a test checks the two agree.

Rules: nothing after the issue hour is used except the observed weather (the labelled stand-in for the
forecast). Flow for the night is the last complete gauge day before issue, exactly as model.inputs does.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from config import MONITORS, TZ
from db import store
from model import blend as blend_mod
from model import calibrate, ensemble, kalman, puff
from model.geo import to_xy
from model.inputs import assemble_met, flow_series, hours, observations
from model.sources import SourceConfig, load_sources

UTC = timezone.utc
TUNE_END = date(2026, 1, 1)   # nights before this tune the model; nights from here on are held out
NIGHT_H = 15                  # 6 PM .. 8 AM
CACHE_DIR = Path(os.getenv("HINDCAST_CACHE", Path(tempfile.gettempdir()) / "smellcast_hindcast"))


@dataclass
class History:
    times: list[datetime]
    met: object
    obs: np.ndarray        # [H, M]
    flow: np.ndarray       # [H] each hour's own gauge day (hindsight; used only for hours before an issue)
    nights: list[date]
    issue_idx: np.ndarray  # [N] index of the 5 PM issue hour
    flow_fc: np.ndarray    # [N, NIGHT_H] flow the forecast may use
    mx: np.ndarray
    my: np.ndarray

    @property
    def night_idx(self) -> np.ndarray:
        return self.issue_idx[:, None] + 1 + np.arange(NIGHT_H)[None, :]

    @property
    def tune(self) -> np.ndarray:
        return np.array([d < TUNE_END for d in self.nights])


def load_history() -> History:
    a, b, _ = store.reading_range()
    start = (a - timedelta(days=3)).astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    n = int((b - start).total_seconds() // 3600) + 1
    times = hours(start, n)
    met, _ = assemble_met(times, ["observed"])
    obs = observations(times)
    flow, _, _ = flow_series(times, times[-1] + timedelta(days=2))
    idx = {t: i for i, t in enumerate(times)}
    nights, issue, flow_fc = [], [], []
    d = (a.astimezone(TZ) - timedelta(days=1)).date()
    while d <= b.astimezone(TZ).date():
        iss = datetime(d.year, d.month, d.day, 17, tzinfo=TZ)
        i = idx.get(iss.astimezone(UTC))
        if i is not None and i >= 24 and i + NIGHT_H < n and np.isfinite(obs[i + 1:i + 1 + NIGHT_H]).sum(axis=0).max() >= 6:
            nights.append(d); issue.append(i)
            flow_fc.append(flow_series(times[i + 1:i + 1 + NIGHT_H], iss)[0])
        d += timedelta(days=1)
    mx, my = to_xy([m.lat for m in MONITORS], [m.lon for m in MONITORS])
    return History(times, met, obs, flow, nights, np.array(issue), np.array(flow_fc), mx, my)


def _cached_unit(met, src: SourceConfig, mx, my) -> np.ndarray:
    """[S, H, M] unit responses, cached on disk by a hash of every input that affects them."""
    h = hashlib.md5()
    for arr in (met.wind_ms, met.wind_dir_deg, met.stab, src.x, src.y, mx, my,
                [src.sigma_v, src.max_age_s, src.sigma_y0, src.sigma_z0, puff.STEP_S]):
        h.update(np.asarray(arr, dtype=np.float64).tobytes())
    h.update(str(met.times[0]).encode())
    path = CACHE_DIR / f"unit_{h.hexdigest()}.npy"
    if path.exists():
        return np.load(path)
    u = puff.simulate_points(met, np.ones(len(met)), src, mx, my)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.save(path, u)
    return u


def member_units(hist: History, src: SourceConfig, n_members: int = ensemble.N_MEMBERS) -> np.ndarray:
    """[n, S, H, M] unit responses per ensemble member (same wind perturbations as model.ensemble)."""
    ddir, sf, _ = ensemble.perturbations(n_members)
    return np.stack([_cached_unit(hist.met.perturbed(ddir[i], sf[i]) if i else hist.met, src, hist.mx, hist.my)
                     for i in range(n_members)])


def fit_physics(hist: History, src: SourceConfig, fit_before: date | None, mask_monitor: int | None = None):
    """Least-squares physics calibration on every hour before fit_before."""
    obs = hist.obs.copy()
    if fit_before is not None:
        cut = datetime(fit_before.year, fit_before.month, fit_before.day, tzinfo=TZ)
        obs[np.array([t >= cut for t in hist.times])] = np.nan
    obs[:6] = np.nan
    if mask_monitor is not None:
        obs[:, mask_monitor] = np.nan
    unit = _cached_unit(hist.met, src, hist.mx, hist.my)
    return calibrate.fit(hist.met, hist.flow, obs, src, hist.mx, hist.my, unit=unit, fit_dilution=True)


@dataclass
class Hindcast:
    hist: History
    src: SourceConfig
    bg: np.ndarray
    physics: np.ndarray      # [N, NIGHT_H, M] ensemble-median physics forecast, ppb
    log_k: np.ndarray        # [N] filter mean at issue
    log_k_var: np.ndarray
    X: np.ndarray            # [N, M, P] correction design rows
    obs_peak: np.ndarray     # [N, M]
    quantiles: np.ndarray | None = None   # [N, M, 3] night-peak P10/P50/P90
    p: np.ndarray | None = None           # [3, N, NIGHT_H, M] hourly P10/P50/P90
    blend: dict | None = None


def run(hist: History, src: SourceConfig, bg: np.ndarray, blend: dict | None = None,
        fit_blend_before: date | None = None, mask_monitor: int | None = None,
        n_members: int = ensemble.N_MEMBERS, base: np.ndarray | None = None) -> Hindcast:
    """Forecast every night. blend given -> use it; else fit it on nights before fit_blend_before.
    mask_monitor: that monitor's readings are never used (leave-one-out); its forecast gets the
    correction interpolated from the other monitors, like any street point."""
    obs = hist.obs.copy()
    M = obs.shape[1]
    others = np.ones(M, bool)
    if mask_monitor is not None:
        obs[:, mask_monitor] = np.nan
        others[mask_monitor] = False
    units = np.tensordot(member_units(hist, src, n_members), src.shares, axes=([1], [0]))   # [n, H, M]
    factor = src.factor(hist.flow, hist.met.temp_c)
    means, variances, _ = kalman.run_series(obs, factor[:, None] * units[0], bg, src.log_k)
    lk, lv = means[hist.issue_idx], variances[hist.issue_idx]
    ni = hist.night_idx
    f_fc = src.factor(hist.flow_fc, hist.met.temp_c[ni])                                    # [N, NIGHT_H]
    _, _, z = ensemble.perturbations(n_members)
    k_mem = np.exp(lk[None, :] + z[:, None] * np.sqrt(np.maximum(lv, 1e-6))[None, :])       # [n, N]
    members = k_mem[:, :, None, None] * f_fc[None, :, :, None] * units[:, ni, :] + bg[None, None, None, :]
    physics = np.median(members, axis=0)                                                    # [N, NIGHT_H, M]

    N = len(hist.nights)
    obs_peak = np.stack([blend_mod.night_peak(obs[ni[k]]) for k in range(N)])
    true_peak = np.stack([blend_mod.night_peak(hist.obs[ni[k]]) for k in range(N)])
    if base is None:
        base = blend["base"] if blend else np.nanmedian(np.log1p(obs_peak[hist.tune]), axis=0)
        base = np.where(np.isfinite(base), base, np.nanmean(base))
    base = np.asarray(base, dtype=float)
    night_no = {d: k for k, d in enumerate(hist.nights)}
    X = np.empty((N, M, 3 * M + 2))
    for k, d in enumerate(hist.nights):
        prev = np.full((blend_mod.WEEK_N, M), np.nan)
        for b in range(1, blend_mod.WEEK_N + 1):
            kk = night_no.get(d - timedelta(days=b))
            if kk is not None:
                prev[b - 1] = obs_peak[kk]
        i = hist.issue_idx[k]
        feats = blend_mod.history_features(prev, obs[i - blend_mod.TODAY_H:i], base)
        X[k] = blend_mod.design(physics[k].max(axis=0), feats)
    out = Hindcast(hist, src, bg, physics, lk, lv, X, true_peak)
    if blend is None and fit_blend_before is not None:
        use = np.array([d < fit_blend_before for d in hist.nights])[:, None] & others[None, :]
        blend = blend_mod.fit(X, obs_peak, use, [m.site_id for m in MONITORS])
        blend["base"] = base.tolist()
        blend["fit_before"] = fit_blend_before.isoformat()
        # hourly (reading / physics) ratios for the P10 curve and the daytime band, same fitting nights
        fit_n = np.array([d < fit_blend_before for d in hist.nights])
        cut = datetime(fit_blend_before.year, fit_blend_before.month, fit_blend_before.day, tzinfo=TZ)
        local_hour = np.array([t.astimezone(TZ).hour for t in hist.times])
        day = np.array([t < cut for t in hist.times]) & ~np.array([blend_mod.is_night_hour(h) for h in local_hour])
        day[:6] = False
        phys_day = np.exp(src.log_k) * factor[:, None] * units[0] + bg[None, :]   # base k: daytime signal is tiny
        blend["hourly_ratio"] = blend_mod.hourly_ratios(
            [obs[ni[fit_n], j].ravel() for j in range(M)], [physics[fit_n][:, :, j].ravel() for j in range(M)],
            [obs[day, j] for j in range(M)], [phys_day[day, j] for j in range(M)])
        if mask_monitor is not None:   # never measured there: take the other monitors' mean
            for v in blend["hourly_ratio"].values():
                v[mask_monitor] = float(np.mean([x for j, x in enumerate(v) if j != mask_monitor]))
    if blend is not None:
        q = blend_mod.predict(blend, X)                                    # [N, M, 3]
        out.p = np.empty((3, N, NIGHT_H, M), dtype=np.float32)
        night = np.ones(NIGHT_H, bool)
        for k in range(N):
            mult = blend_mod.multipliers(blend_mod.scales(q[k], physics[k].max(axis=0)), blend.get("hourly_ratio"))
            if mask_monitor is not None:   # held-out monitor: correction interpolated from the others
                mult[mask_monitor] = blend_mod.spread_scales(mult, hist.mx, hist.my, hist.mx[[mask_monitor]],
                                                             hist.my[[mask_monitor]], use=others)[0]
                q[k, mask_monitor] = mult[mask_monitor, :3] * physics[k, :, mask_monitor].max()
            out.p[:, k] = blend_mod.hourly_quantiles(physics[k], night, mult)
        out.quantiles, out.blend = q, blend
    return out


def calibrate_all(fit_before: date | None = TUNE_END, mask_monitor: int | None = None):
    """Physics fit + correction fit on data before fit_before. Returns (Hindcast, calibration dict)."""
    hist = load_history()
    res = fit_physics(hist, load_sources(), fit_before, mask_monitor)
    src = load_sources().with_params(log_k=res.log_k, alpha=res.alpha, beta=res.beta, shares=res.shares,
                                     q_dil=res.q_dil, dil_gamma=res.dil_gamma)
    bg = np.asarray(res.background, dtype=float)
    if mask_monitor is not None:   # no readings there: it gets the mean background, like a street point
        bg = bg.copy(); bg[mask_monitor] = np.delete(bg, mask_monitor).mean()
    hc = run(hist, src, bg, fit_blend_before=fit_before or (hist.nights[-1] + timedelta(days=1)), mask_monitor=mask_monitor)
    cal = {"log_k": res.log_k, "alpha": res.alpha, "beta": res.beta, "shares": res.shares.tolist(),
           "background": bg.tolist(), "q_dil_mgd": res.q_dil, "dil_gamma": res.dil_gamma,
           "sigma_v_ms": src.sigma_v, "rmse_log": res.rmse_log, "n_obs": res.n_obs, "blend": hc.blend,
           "fit_before": fit_before.isoformat() if fit_before else None}
    return hc, cal


def baseline_arrays(hist: History, days: int = 30) -> dict[str, np.ndarray]:
    """Persistence and climatology [N, NIGHT_H, M], same definitions as validate.baselines."""
    ni = hist.night_idx
    pers = hist.obs[ni - 24]
    local_hour = np.array([t.astimezone(TZ).hour for t in hist.times])
    clim = np.full(pers.shape, np.nan)
    for k, i in enumerate(hist.issue_idx):
        a = max(i - days * 24, 0)
        o, hh = hist.obs[a:i], local_hour[a:i]
        for q in range(NIGHT_H):
            s = o[hh == local_hour[ni[k, q]]]
            ok = np.isfinite(s)
            if len(s):
                clim[k, q] = np.where(ok.any(axis=0), np.where(ok, s, 0).sum(axis=0) / np.maximum(ok.sum(axis=0), 1), np.nan)
    return {"persistence": pers, "climatology": clim}


def score(hc: Hindcast, p50: np.ndarray | None = None, p90: np.ndarray | None = None) -> dict:
    """Tuning / held-out scores for a hindcast (or any [N, NIGHT_H, M] forecast on its nights)."""
    from validate import metrics
    hist = hc.hist
    obs = hist.obs[hist.night_idx]
    base = baseline_arrays(hist)
    p50 = hc.p[1] if p50 is None else p50
    p90 = hc.p[2] if p90 is None else p90
    prev = blend_mod_prev_peak(hist)
    out = {}
    for name, sel in (("tuning", hist.tune), ("held_out", ~hist.tune)):
        r = metrics.evaluate(obs, {"model": p50, **base}, prev, [m.site_id for m in MONITORS], sel, {"model_possible": p90})
        r["coverage"] = metrics.coverage(obs, p90, r["eligible"])
        out[name] = r
    return out


def blend_mod_prev_peak(hist: History) -> np.ndarray:
    """[N, M] observed peak of the night before each night (NaN if not available)."""
    return np.stack([blend_mod.night_peak(hist.obs[hist.night_idx[k] - 24]) for k in range(len(hist.nights))])


def brief(sc: dict, site: str = "all") -> str:
    """One line per period and method: hit rate / false-alarm ratio, category accuracy, log MAE."""
    lines = []
    for period, r in sc.items():
        b = r["binary"]["all_nights"][site]; s = r["summary"]
        for rule, c in b.items():
            m = "model" if rule.startswith("model") else rule
            extra = f" cat={s[m][site]['category_accuracy']:.3f} mae={s[m][site]['mae_log']:.3f}" if rule != "model_possible" else ""
            hr = "  n/a" if c["hit_rate"] is None else f"{c['hit_rate']:.3f}"
            fr = "  n/a" if c["false_alarm_ratio"] is None else f"{c['false_alarm_ratio']:.3f}"
            lines.append(f"{period:9s} {site:10s} {rule:15s} hit={hr} far={fr} alarms={c['hits'] + c['false_alarms']:4d} "
                         f"orange={c['hits'] + c['misses']:4d} n={c['n']:5d}{extra}")
        cv = r["coverage"]
        lines.append(f"{period:9s} coverage: night peak under P90 {cv['night_peak_under_p90']:.3f}, hourly under P90 {cv['hourly_under_p90']:.3f}")
    return "\n".join(lines)
