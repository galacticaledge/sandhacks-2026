"""Online calibration: scalar Kalman filter on log k_t as a random walk (spec 5.4)."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

Q_PER_HOUR = 0.02     # random-walk variance added per hour (log units^2)
R_BASE = 0.35         # observation variance floor (log units^2)
MIN_SIGNAL_PPB = 0.3  # ignore a monitor-hour when the model says it is not downwind


@dataclass
class LogKFilter:
    mean: float
    var: float = 1.0
    q: float = Q_PER_HOUR

    def predict(self, hours: float = 1.0):
        self.var += self.q * hours

    def update(self, obs_ppb: float, unit_ppb: float, background: float) -> bool:
        """unit_ppb = modelled concentration at the monitor for log k = 0 (i.e. k = 1).
        Returns True if the observation was informative and used."""
        if obs_ppb is None or not np.isfinite(obs_ppb) or unit_ppb <= 0:
            return False
        predicted_signal = math.exp(self.mean) * unit_ppb
        if predicted_signal < MIN_SIGNAL_PPB and obs_ppb - background < 2.0:
            return False
        if predicted_signal < 0.05:
            return False  # monitor clearly off-axis: a high reading is a wind error, not a k error
        y = math.log(max(obs_ppb - background, 0.1)) - math.log(unit_ppb)
        r = R_BASE + 1.0 / (1.0 + predicted_signal)
        gain = self.var / (self.var + r)
        self.mean += gain * (y - self.mean)
        self.var *= (1 - gain)
        return True


def relax_toward(log_k_now: float, log_k_median: float, lead_hours: np.ndarray, tau_h: float = 12.0) -> np.ndarray:
    """Linear relaxation from the current filter mean to the 30-day median over tau hours."""
    w = np.clip(1 - np.asarray(lead_hours, dtype=float) / tau_h, 0, 1)
    return log_k_median + (log_k_now - log_k_median) * w
