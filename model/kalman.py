"""Online calibration: scalar Kalman filter on log k_t as a random walk (spec 5.4).

An hour is used only when the model, run with the calibrated base k, puts real signal on the monitor.
The gate uses the base k (not the filter's own state) so a filter that has drifted low cannot lock
itself out, and plume-edge hours with a near-zero prediction cannot swing k by large factors.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

Q_PER_HOUR = 0.005        # random-walk variance added per hour (log units^2)
R_OBS = 2.0               # observation variance (log units^2): one hour is a noisy view of k
MIN_REF_SIGNAL_PPB = 0.1  # ignore a monitor-hour when the base model says it is not downwind
RELAX_TAU_H = float("inf")  # episodes last days: k is held through the 24 h forecast (spec said 12 h)


@dataclass
class LogKFilter:
    mean: float
    var: float = 1.0
    q: float = Q_PER_HOUR
    r: float = R_OBS
    ref: float | None = None  # calibrated base log k for the gate; None = use the starting mean

    def __post_init__(self):
        if self.ref is None:
            self.ref = self.mean

    def predict(self, hours: float = 1.0):
        self.var += self.q * hours

    def update(self, obs_ppb: float, unit_ppb: float, background: float) -> bool:
        """unit_ppb = modelled concentration at the monitor for log k = 0 (i.e. k = 1).
        Returns True if the observation was informative and used."""
        if obs_ppb is None or not np.isfinite(obs_ppb) or unit_ppb <= 0:
            return False
        if math.exp(self.ref) * unit_ppb < MIN_REF_SIGNAL_PPB:
            return False  # monitor off-axis: a high reading is a wind error, not a k error
        y = math.log(max(obs_ppb - background, 0.1)) - math.log(unit_ppb)
        gain = self.var / (self.var + self.r)
        self.mean += gain * (y - self.mean)
        self.var *= (1 - gain)
        return True


def run_series(obs: np.ndarray, unit: np.ndarray, background: np.ndarray, ref_log_k: float,
               mean0: float | None = None, var0: float = 1.0) -> tuple[np.ndarray, np.ndarray, int]:
    """Filter a whole [H, M] history. Returns (mean, var) of length H + 1: entry h is the state
    using observations from hours before h only. Also the number of observations used."""
    H, M = obs.shape
    f = LogKFilter(mean=ref_log_k if mean0 is None else mean0, var=var0, ref=ref_log_k)
    means = np.empty(H + 1); variances = np.empty(H + 1)
    used = 0
    for h in range(H):
        means[h], variances[h] = f.mean, f.var
        f.predict()
        for j in range(M):
            used += f.update(obs[h, j], float(unit[h, j]), float(background[j]))
    means[H], variances[H] = f.mean, f.var
    return means, variances, used


def relax_toward(log_k_now: float, log_k_median: float, lead_hours: np.ndarray, tau_h: float = 12.0) -> np.ndarray:
    """Linear relaxation from the current filter mean to the long-run value over tau hours."""
    w = np.clip(1 - np.asarray(lead_hours, dtype=float) / tau_h, 0, 1)
    return log_k_median + (log_k_now - log_k_median) * w
