"""Hourly emission rate E_t = k_t * Q_t^alpha * exp(beta (T_t - T_ref)) / (1 + (Q_t / Q_dil)^gamma)  [g/s].

Spec 5.2 plus one fitted term: above about Q_dil the river is mostly storm water, which dilutes
the sewage, so the release stops growing with flow and falls. Q_dil = 0 switches the term off.
"""
from __future__ import annotations

import numpy as np

UG_M3_TO_PPB = 24.45 / 34.08


def emission_factor(flow_mgd, temp_c, alpha: float, beta: float, t_ref: float = 15.0,
                    q_dil: float = 0.0, gamma: float = 2.0) -> np.ndarray:
    """Everything in E except k."""
    q = np.maximum(np.asarray(flow_mgd, dtype=float), 0.0)
    f = q ** alpha * np.exp(beta * (np.asarray(temp_c, dtype=float) - t_ref))
    if q_dil and q_dil > 0:
        f = f / (1.0 + (q / q_dil) ** gamma)
    return f


def emission_rate(log_k, flow_mgd, temp_c, alpha: float, beta: float, t_ref: float = 15.0,
                  q_dil: float = 0.0, gamma: float = 2.0) -> np.ndarray:
    return np.exp(np.asarray(log_k, dtype=float)) * emission_factor(flow_mgd, temp_c, alpha, beta, t_ref, q_dil, gamma)


def ug_m3_to_ppb(c):
    return np.asarray(c) * UG_M3_TO_PPB


def ppb_to_ug_m3(c):
    return np.asarray(c) / UG_M3_TO_PPB
