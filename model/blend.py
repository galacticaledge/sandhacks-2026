"""Monitor correction: the physics forecast corrected by the monitors' own history.

The puff model answers "where does the gas go"; this layer answers "how high will tonight's peak be"
at each monitor. It is one linear regression on log(1 + night peak ppb), fitted on past nights:

    log1p(peak) = a_m + b_m * log1p(physics peak tonight)      <- puff model, flow, weather, filter
                      + c_m * log1p(last night's observed peak)
                      + d   * mean log1p(peak) over the last 7 nights
                      + e   * log1p(highest reading in the 8 h before issue)

P10 / P50 / P90 of the night peak are that prediction plus the 10th / 50th / 90th percentile of the
regression's own past errors at that monitor (no bell-curve assumption, so heavy tails are kept).

Hourly curves (hourly_quantiles): the physics curve is the hour-by-hour middle estimate. A night's peak
is a spike of a few hours, far above the typical hour, so
  P50: the three highest physics hours of the night are lifted toward the P50 night peak (fully at the
       top hour, then 2/3 and 1/3); every other hour keeps the physics value;
  P90: every night hour is scaled so the night maximum equals the P90 night peak;
  P10: physics times the 10th percentile of past (reading / physics) ratios.
Daytime hours use past daytime ratios only. All multipliers are spread over the street grid by
inverse-distance weighting, so the map agrees with the monitors.
No LLM, no future data: every input is known at issue time.
"""
from __future__ import annotations

import numpy as np

NIGHT_START_H, NIGHT_END_H = 18, 9   # 6 PM -> 9 AM local, same window the alerts use
MIN_NIGHT_HOURS = 6
TODAY_H = 8                          # hours before issue for the "today" feature
WEEK_N = 7
TODAY_FILL = 0.5
FEATURES = ["physics", "last_night", "week", "today"]
SPIKE_WEIGHTS = (1.0, 2 / 3, 1 / 3)   # share of the P50 correction given to the 1st, 2nd, 3rd highest hour
MULT_COLS = ("p10", "p50", "p90", "night_p10", "day_p10", "day_p90")


def is_night_hour(local_hour: int) -> bool:
    return local_hour >= NIGHT_START_H or local_hour < NIGHT_END_H


def night_peak(values: np.ndarray) -> np.ndarray:
    """values [hours, M] for one night -> peak per monitor, NaN when fewer than MIN_NIGHT_HOURS readings."""
    v = np.asarray(values, dtype=float)
    ok = np.isfinite(v)
    peak = np.where(ok, v, -np.inf).max(axis=0)
    return np.where(ok.sum(axis=0) >= MIN_NIGHT_HOURS, peak, np.nan)


def history_features(prev_peaks: np.ndarray, today: np.ndarray, base: np.ndarray) -> dict[str, np.ndarray]:
    """prev_peaks [WEEK_N, M]: observed night peaks, most recent first (NaN = missing).
    today [hours, M]: readings in the TODAY_H hours before issue. base [M]: fallback level, log1p ppb."""
    lp = np.log1p(np.clip(np.asarray(prev_peaks, dtype=float), 0, None))
    have = np.isfinite(lp)
    week = np.where(have.any(axis=0), np.where(have, lp, 0).sum(axis=0) / np.maximum(have.sum(axis=0), 1), base)
    last = np.where(have[0], lp[0], week)
    t = np.asarray(today, dtype=float)
    tmax = np.where(np.isfinite(t), t, -np.inf).max(axis=0)
    today_f = np.where(np.isfinite(t).any(axis=0), np.log1p(np.clip(tmax, 0, None)), TODAY_FILL)
    return {"last_night": last, "week": week, "today": today_f}


def design(physics_peak: np.ndarray, hist: dict[str, np.ndarray]) -> np.ndarray:
    """One night -> [M, 3M + 2] design rows: intercept, physics slope and last-night slope per monitor,
    shared week and today slopes."""
    M = len(physics_peak)
    eye = np.eye(M)
    phys = np.log1p(np.clip(np.asarray(physics_peak, dtype=float), 0, None))
    return np.concatenate([eye, eye * phys[:, None], eye * hist["last_night"][:, None],
                           hist["week"][:, None], hist["today"][:, None]], axis=1)


def fit(X: np.ndarray, peaks: np.ndarray, use: np.ndarray | None = None, site_ids: list[str] | None = None) -> dict:
    """X [N, M, P] design rows, peaks [N, M] observed night peaks (NaN = no label). use [N, M] optional mask."""
    y = np.log1p(np.clip(peaks, 0, None))
    ok = np.isfinite(y) & np.isfinite(X).all(axis=2)
    if use is not None:
        ok &= use
    coef = np.linalg.lstsq(X[ok], y[ok], rcond=None)[0]
    res = np.where(ok, y - X @ coef, np.nan)
    M = y.shape[1]
    pooled = np.percentile(res[ok], [10, 50, 90])
    q = [(np.nanpercentile(res[:, j], [10, 50, 90]) if ok[:, j].sum() >= 50 else pooled).tolist() for j in range(M)]
    return {"features": FEATURES, "coef": coef.tolist(), "resid_q": q, "resid_q_pooled": pooled.tolist(),
            "rmse_log": float(np.sqrt(np.mean(res[ok] ** 2))), "n": int(ok.sum()),
            "n_per_monitor": ok.sum(axis=0).astype(int).tolist(), "site_ids": site_ids}


def predict(blend: dict, X: np.ndarray) -> np.ndarray:
    """X [..., M, P] -> night-peak quantiles [..., M, 3] in ppb (P10, P50, P90)."""
    mu = X @ np.asarray(blend["coef"])
    q = np.asarray(blend["resid_q"])
    return np.clip(np.expm1(mu[..., None] + q), 0.0, None)


def contributions(blend: dict, X: np.ndarray) -> list[dict]:
    """Per monitor, how much each input moves tonight's log1p(peak): shown with the forecast."""
    coef = np.asarray(blend["coef"]); M = X.shape[0]
    t = X * coef
    return [{"intercept": float(t[j, :M].sum()), "physics": float(t[j, M:2 * M].sum()),
             "last_night": float(t[j, 2 * M:3 * M].sum()), "week": float(t[j, 3 * M]), "today": float(t[j, 3 * M + 1])}
            for j in range(M)]


def scales(quantiles: np.ndarray, physics_peak: np.ndarray) -> np.ndarray:
    """[M, 3] multipliers that take the physics night peak at each monitor to each quantile."""
    return np.asarray(quantiles) / np.maximum(np.asarray(physics_peak, dtype=float), 1e-3)[:, None]


def spread_scales(scale: np.ndarray, mx, my, x, y, use: np.ndarray | None = None) -> np.ndarray:
    """Inverse-distance-squared weighting of log multipliers from monitors to points. Returns [N, K]
    for scale [M, K]. A point on a monitor gets that monitor's values."""
    mx = np.asarray(mx, dtype=float); my = np.asarray(my, dtype=float)
    s = np.log(np.maximum(np.asarray(scale, dtype=float), 1e-3))
    if use is not None:
        mx, my, s = mx[use], my[use], s[use]
    d2 = (np.asarray(x, dtype=float)[:, None] - mx[None, :]) ** 2 + (np.asarray(y, dtype=float)[:, None] - my[None, :]) ** 2
    w = 1.0 / np.maximum(d2, 1.0)
    w /= w.sum(axis=1, keepdims=True)
    return np.exp(w @ s)


def hourly_ratios(obs_night, phys_night, obs_day, phys_day) -> dict:
    """Past (reading / physics) ratio percentiles per monitor. Inputs are lists of 1-D arrays, one per monitor."""
    def q(o, p, pct, default):
        ok = np.isfinite(o) & np.isfinite(p) & (p > 0)
        return float(np.percentile(o[ok] / p[ok], pct)) if ok.sum() >= 50 else default
    return {"night_p10": [q(o, p, 10, 0.3) for o, p in zip(obs_night, phys_night)],
            "day_p10": [q(o, p, 10, 0.3) for o, p in zip(obs_day, phys_day)],
            "day_p90": [max(q(o, p, 90, 2.0), 1.0) for o, p in zip(obs_day, phys_day)]}


def multipliers(scale: np.ndarray, ratios: dict | None) -> np.ndarray:
    """[M, 6] per-monitor multipliers in MULT_COLS order: night-peak scales, then hourly ratios."""
    M = len(scale)
    r = ratios or {"night_p10": [0.3] * M, "day_p10": [0.3] * M, "day_p90": [2.0] * M}
    return np.concatenate([np.asarray(scale, dtype=float),
                           np.array([r["night_p10"], r["day_p10"], r["day_p90"]], dtype=float).T], axis=1)


def hourly_quantiles(physics: np.ndarray, night: np.ndarray, mult: np.ndarray):
    """physics [H, N] ppb, night [H] bool, mult [N, 6] (MULT_COLS). Returns p10, p50, p90 [H, N].
    The night maximum of p50 / p90 equals physics night peak * mult p50 / p90 (the night-peak quantiles)."""
    physics = np.asarray(physics, dtype=np.float32)
    night = np.asarray(night, bool)
    mult = np.asarray(mult, dtype=np.float32)
    w = np.zeros(physics.shape, dtype=np.float32)
    if night.any():
        pn = physics[night]
        rank = np.argsort(np.argsort(-pn, axis=0, kind="stable"), axis=0, kind="stable")   # 0 = highest hour
        wn = np.zeros(pn.shape, dtype=np.float32)
        for r, v in enumerate(SPIKE_WEIGHTS):
            wn[rank == r] = v
        w[night] = wn
    p50 = physics * mult[None, :, 1] ** w
    nt = night[:, None]
    p90 = np.where(nt, np.maximum(physics * mult[None, :, 2], p50), physics * mult[None, :, 5])
    p10 = np.where(nt, np.minimum(physics * mult[None, :, 3], p50), physics * mult[None, :, 4])
    return p10, p50, np.maximum(p90, p50)
