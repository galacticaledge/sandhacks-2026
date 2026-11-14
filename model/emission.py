"""Hourly emission rate E_t = k_t * Q_t^alpha * exp(beta (T_t - T_ref))  [g/s] (spec 5.2)."""
from __future__ import annotations

import numpy as np

UG_M3_TO_PPB = 24.45 / 34.08


def emission_factor(flow_mgd, temp_c, alpha: float, beta: float, t_ref: float = 15.0) -> np.ndarray:
    """Everything in E except k: Q^alpha * exp(beta (T - T_ref))."""
    q = np.maximum(np.asarray(flow_mgd, dtype=float), 0.0)
    return q ** alpha * np.exp(beta * (np.asarray(temp_c, dtype=float) - t_ref))


def emission_rate(log_k, flow_mgd, temp_c, alpha: float, beta: float, t_ref: float = 15.0) -> np.ndarray:
    return np.exp(np.asarray(log_k, dtype=float)) * emission_factor(flow_mgd, temp_c, alpha, beta, t_ref)


def ug_m3_to_ppb(c):
    return np.asarray(c) * UG_M3_TO_PPB


def ppb_to_ug_m3(c):
    return np.asarray(c) / UG_M3_TO_PPB
