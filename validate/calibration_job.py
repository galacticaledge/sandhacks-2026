"""Fit offline calibration (spec 5.4) on the monitor history with observed weather.

python -m validate.calibration_job            # fit on everything, write data/calibration.json
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import numpy as np

from config import MONITORS, TZ
from db import store
from model import calibrate
from model.geo import to_xy
from model.inputs import CALIBRATION_PATH, assemble_met, flow_series, hours, observations
from model.sources import load_sources

log = logging.getLogger("calibrate")
UTC = timezone.utc
MIN_HOURS = 24
MIN_HOURS_REPLAY = 48


def fit_window(start: datetime, end: datetime, mask_monitor: int | None = None):
    """Returns (CalibrationResult, met, flow, obs, unit) or None if not enough data."""
    start = start.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    n = int((end - start).total_seconds() // 3600)
    if n < MIN_HOURS:
        return None
    times = hours(start, n)
    try:
        met, _ = assemble_met(times, ["observed"])
    except RuntimeError:
        return None
    flow, _, _ = flow_series(times, end)
    obs = observations(times)
    obs[:4] = np.nan  # puff spin-up
    if mask_monitor is not None:
        obs[:, mask_monitor] = np.nan
    if np.isfinite(obs).sum() < MIN_HOURS:
        return None
    src = load_sources()
    mx, my = to_xy([m.lat for m in MONITORS], [m.lon for m in MONITORS])
    unit = calibrate.unit_responses(met, src, mx, my)
    res = calibrate.fit(met, flow, obs, src, mx, my, unit=unit)
    return res, met, flow, obs, unit


def params_from(res):
    src = load_sources().with_params(log_k=res.log_k, alpha=res.alpha, beta=res.beta, shares=res.shares)
    cal = {"log_k": res.log_k, "alpha": res.alpha, "beta": res.beta, "shares": res.shares.tolist(),
           "background": res.background.tolist(), "rmse_log": res.rmse_log, "n_obs": res.n_obs}
    return src, np.asarray(res.background), cal


def params_before(t: datetime, max_days: int = 120):
    """Calibration using only data before t (for honest replays). Falls back to priors."""
    a, b, n = store.reading_range()
    if not a:
        return None
    start = max(a, t - timedelta(days=max_days))
    if (t - start).total_seconds() < MIN_HOURS_REPLAY * 3600:
        return None
    out = fit_window(start, t)
    return params_from(out[0]) if out else None


def run_calibration() -> dict | None:
    a, b, n = store.reading_range()
    if not a:
        return None
    out = fit_window(max(a, b - timedelta(days=120)), b + timedelta(hours=1))
    if not out:
        log.warning("not enough data to calibrate")
        return None
    res = out[0]
    cal = params_from(res)[2]
    cal["fitted_at"] = datetime.now(UTC).isoformat()
    cal["window"] = [a.isoformat(), b.isoformat()]
    CALIBRATION_PATH.write_text(json.dumps(cal, indent=1))
    log.info("calibration: %s", cal)
    return cal


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_calibration(), indent=1))
