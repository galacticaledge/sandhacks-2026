"""Gaussian puff dispersion (spec 5.3, primary model).

A puff leaves each source every 10 minutes and is moved by that hour's wind. Its spread
grows with travel distance on Pasquill-Gifford (Briggs rural) curves. Each 10-minute step
integrates the puff's ground-level concentration analytically along its straight-line path
(a "slug"), so receptors see a smooth hourly average instead of puff-sized beads.
Output: hourly-average ppb at 1.5 m.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.special import erf

from model.emission import ug_m3_to_ppb
from model.met import WIND_FLOOR_MS, Met
from model.sources import SourceConfig
from model.stability import sigma_y, sigma_z

STEP_S = 600.0
MAX_AGE_S = 4 * 3600.0
SQRT2 = math.sqrt(2.0)
NORM = (2 * math.pi) ** 1.5


def simulate(met: Met, emis_gps: np.ndarray, src: SourceConfig, rx: np.ndarray, ry: np.ndarray,
             z: float = 1.5, per_source: bool = False, max_age_s: float = MAX_AGE_S) -> np.ndarray:
    """Hourly mean ppb at receptors.

    emis_gps: total release per hour, g/s (split across sources by src.shares).
    per_source: return [S, H, N] unit-share responses instead of the summed [H, N].
    """
    rx = np.asarray(rx, dtype=np.float32)[None, :]
    ry = np.asarray(ry, dtype=np.float32)[None, :]
    H, N, S = len(met), rx.shape[1], len(src.ids)
    out = np.zeros((S if per_source else 1, H, N), dtype=np.float32)
    steps = int(round(3600 / STEP_S))

    # puff state
    px = np.empty(0, np.float32); py = np.empty(0, np.float32)
    dist = np.empty(0, np.float32); age = np.empty(0, np.float32)
    mass = np.empty(0, np.float32); sid = np.empty(0, np.int16)
    vert = 2.0  # ground reflection for a ground-level source: exp terms combine to 2*exp(-z^2/2sz^2)

    for h in range(H):
        u = max(float(met.wind_ms[h]), WIND_FLOOR_MS)
        theta = math.radians(float(met.wind_dir_deg[h]))
        ex, ey = -math.sin(theta), -math.cos(theta)  # unit vector the air moves toward
        cls = int(met.stab[h])
        L = u * STEP_S
        for _ in range(steps):
            # release
            m = (float(emis_gps[h]) * STEP_S * (np.ones(S) if per_source else src.shares)).astype(np.float32)
            px = np.concatenate([px, src.x.astype(np.float32)])
            py = np.concatenate([py, src.y.astype(np.float32)])
            dist = np.concatenate([dist, np.zeros(S, np.float32)])
            age = np.concatenate([age, np.zeros(S, np.float32)])
            mass = np.concatenate([mass, m])
            sid = np.concatenate([sid, np.arange(S, dtype=np.int16)])

            dx = rx - px[:, None]
            dy = ry - py[:, None]
            a = dx * ex + dy * ey          # along-track distance from segment start
            n = -dx * ey + dy * ex         # cross-track
            # spread at the receptor's own position along the segment (slug treatment)
            s_r = dist[:, None] + np.clip(a, 0.0, L)
            sy = np.sqrt(src.sigma_y0 ** 2 + sigma_y(s_r, cls) ** 2)
            sz = np.sqrt(src.sigma_z0 ** 2 + sigma_z(s_r, cls) ** 2)
            along = (sy / u) * math.sqrt(math.pi / 2) * (erf(a / (sy * SQRT2)) - erf((a - L) / (sy * SQRT2)))
            peak = mass[:, None] * vert * np.exp(-z * z / (2 * sz * sz)) / (NORM * sy * sy * sz)
            dose = peak * np.exp(-n * n / (2 * sy * sy)) * along  # g*s/m^3 over this step
            if per_source:
                for s in range(S):
                    sel = sid == s
                    if sel.any():
                        out[s, h] += dose[sel].sum(axis=0)
            else:
                out[0, h] += dose.sum(axis=0)

            # advance and retire
            px = px + ex * L; py = py + ey * L
            dist = dist + L; age = age + STEP_S
            keep = (age < max_age_s) & (np.abs(px) < 12_000) & (np.abs(py) < 12_000)
            px, py, dist, age, mass, sid = px[keep], py[keep], dist[keep], age[keep], mass[keep], sid[keep]

    # g*s/m^3 accumulated over the hour -> hourly mean g/m^3 -> ug/m^3 -> ppb
    out = ug_m3_to_ppb(out / 3600.0 * 1e6).astype(np.float32)
    return out if per_source else out[0]
