"""Offline calibration (spec 5.4): least squares on log(C + 1) at the monitors.

Fits base log k, alpha, beta, source shares and a background per monitor. Unit responses
per source come from the puff model run with E = 1 g/s; the hour's emission factor is applied
at the receptor hour (puffs live <= 4 h, so this lag approximation is small).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from model import puff
from model.emission import emission_factor
from model.met import Met
from model.sources import SourceConfig

PRIOR_SD = {"log_k": 2.0, "alpha": 0.3, "beta": 0.03, "share_logit": 0.7}


@dataclass
class CalibrationResult:
    log_k: float
    alpha: float
    beta: float
    shares: np.ndarray
    background: np.ndarray  # per monitor ppb
    rmse_log: float
    n_obs: int
    success: bool


def unit_responses(met: Met, src: SourceConfig, mx, my) -> np.ndarray:
    """[S, H, M] ppb at monitors per source for 1 g/s."""
    return puff.simulate(met, np.ones(len(met)), src, mx, my, per_source=True)


def fit(met: Met, flow_mgd: np.ndarray, obs: np.ndarray, src: SourceConfig, mx, my,
        unit: np.ndarray | None = None) -> CalibrationResult:
    """obs: [H, M] observed ppb (NaN = missing)."""
    if unit is None:
        unit = unit_responses(met, src, mx, my)
    S, H, M = unit.shape
    ok = np.isfinite(obs)
    y = np.log(np.clip(obs[ok], 0, None) + 1)

    def unpack(p):
        logk, alpha, beta = p[0], p[1], p[2]
        logits = np.concatenate([[0.0], p[3:3 + S - 1]])
        shares = np.exp(logits) / np.exp(logits).sum()
        bg = p[3 + S - 1:]
        return logk, alpha, beta, shares, bg

    def model(p):
        logk, alpha, beta, shares, bg = unpack(p)
        f = emission_factor(flow_mgd, met.temp_c, alpha, beta, src.t_ref)
        c = np.exp(logk) * f[:, None] * np.tensordot(shares, unit, axes=(0, 0)) + bg[None, :]
        return c

    def resid(p):
        c = model(p)
        r = np.log(np.clip(c[ok], 0, None) + 1) - y
        prior = [(p[1] - src.alpha) / PRIOR_SD["alpha"], (p[2] - src.beta) / PRIOR_SD["beta"]]
        prior += list((p[3:3 + S - 1] - logit0) / PRIOR_SD["share_logit"])
        prior.append((p[0] - src.log_k) / PRIOR_SD["log_k"])
        return np.concatenate([r, prior])

    logit0 = np.log(src.shares[1:] / src.shares[0])
    p0 = np.concatenate([[src.log_k, src.alpha, src.beta],
                         np.log(src.shares[1:] / src.shares[0]), np.full(M, 0.45)])
    lo = np.concatenate([[-20, 0.3, 0.0], np.full(S - 1, -6), np.zeros(M)])
    hi = np.concatenate([[10, 2.0, 0.15], np.full(S - 1, 6), np.full(M, 2.0)])
    sol = least_squares(resid, np.clip(p0, lo + 1e-6, hi - 1e-6), bounds=(lo, hi))
    logk, alpha, beta, shares, bg = unpack(sol.x)
    rmse = float(np.sqrt(np.mean(sol.fun[:int(ok.sum())] ** 2))) if ok.any() else float("nan")
    return CalibrationResult(float(logk), float(alpha), float(beta), shares, bg, rmse, int(ok.sum()), bool(sol.success))
