"""Monitor correction: the physics forecast corrected by the monitors' own history.

The puff model answers "where does the gas go"; this layer answers "how high will tonight's peak be"
at each monitor. It is one linear regression on log(1 + night peak ppb), fitted on past nights:

    log1p(peak) = a_m + b_m * log1p(physics peak tonight)      <- puff model, flow, weather, filter
                      + c_m * log1p(last night's observed peak)
                      + d   * mean log1p(peak) over the last 7 nights
                      + e   * log1p(highest reading in the 8 h before issue)

P10 / P50 / P90 of the night peak are that prediction plus the 10th / 50th / 90th percentile of the
regression's own past errors at that monitor (no bell-curve assumption, so heavy tails are kept).
The hourly physics curve is then scaled so its night maximum equals each quantile, and the scale is
spread over the street grid by inverse-distance weighting, so the map agrees with the monitors.
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
    """Inverse-distance-squared weighting of log scale from monitors to points. Returns [N, 3].
    A point on a monitor gets that monitor's scale."""
    mx = np.asarray(mx, dtype=float); my = np.asarray(my, dtype=float)
    s = np.log(np.maximum(np.asarray(scale, dtype=float), 1e-6))
    if use is not None:
        mx, my, s = mx[use], my[use], s[use]
    d2 = (np.asarray(x, dtype=float)[:, None] - mx[None, :]) ** 2 + (np.asarray(y, dtype=float)[:, None] - my[None, :]) ** 2
    w = 1.0 / np.maximum(d2, 1.0)
    w /= w.sum(axis=1, keepdims=True)
    return np.exp(w @ s)
