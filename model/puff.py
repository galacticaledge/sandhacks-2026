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
from model.geo import retire_m
from model.met import WIND_FLOOR_MS, Met
from model.sources import SourceConfig
from model.stability import sigma_y, sigma_z

STEP_S = 600.0
MAX_AGE_S = 4 * 3600.0
RETIRE_M = retire_m()   # was a fixed 12 km; now follows the forecast box (config.BBOX)
SQRT2 = math.sqrt(2.0)
NORM = (2 * math.pi) ** 1.5


def simulate(met: Met, emis_gps: np.ndarray, src: SourceConfig, rx: np.ndarray, ry: np.ndarray,
             z: float = 1.5, per_source: bool = False, max_age_s: float | None = None) -> np.ndarray:
    """Hourly mean ppb at receptors.

    emis_gps: total release per hour, g/s (split across sources by src.shares).
    per_source: return [S, H, N] unit-share responses instead of the summed [H, N].
    """
    max_age_s = src.max_age_s if max_age_s is None else max_age_s
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
            if src.sigma_v > 0:  # meander: the wind direction wanders within the hour, widening the hour-average puff
                sy = np.sqrt(sy ** 2 + (src.sigma_v * (age[:, None] + np.clip(a, 0.0, L) / u)) ** 2)
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
            keep = (age < max_age_s) & (np.abs(px) < RETIRE_M) & (np.abs(py) < RETIRE_M)
            px, py, dist, age, mass, sid = px[keep], py[keep], dist[keep], age[keep], mass[keep], sid[keep]

    # g*s/m^3 accumulated over the hour -> hourly mean g/m^3 -> ug/m^3 -> ppb
    out = ug_m3_to_ppb(out / 3600.0 * 1e6).astype(np.float32)
    return out if per_source else out[0]


def simulate_points(met: Met, emis_gps: np.ndarray, src: SourceConfig, rx, ry, z: float = 1.5,
                    chunk: int = 4000) -> np.ndarray:
    """Same physics as simulate(per_source=True), vectorised over release times instead of looping over
    them. Fast for a few receptors over a long history (calibration, replays): [S, H, N] ppb for unit shares.

    A puff released at step i sits, at step j, at source + (sum of wind displacements over steps i..j-1),
    so positions come from cumulative sums and every (release, age) pair is evaluated at once.
    """
    rx = np.asarray(rx, dtype=np.float64); ry = np.asarray(ry, dtype=np.float64)
    H, N, S = len(met), rx.size, len(src.ids)
    steps = int(round(3600 / STEP_S))
    A = int(round(src.max_age_s / STEP_S))
    T = H * steps
    u = np.repeat(np.maximum(met.wind_ms, WIND_FLOOR_MS), steps)
    th = np.radians(np.repeat(met.wind_dir_deg, steps))
    ex, ey = -np.sin(th), -np.cos(th)
    cls = np.repeat(np.asarray(met.stab, dtype=int), steps)
    L = u * STEP_S
    pad = np.zeros(A)
    cx = np.concatenate([[0.0], np.cumsum(ex * L), pad + np.sum(ex * L)])
    cy = np.concatenate([[0.0], np.cumsum(ey * L), pad + np.sum(ey * L)])
    cp = np.concatenate([[0.0], np.cumsum(L), pad + np.sum(L)])
    mass = np.repeat(np.asarray(emis_gps, dtype=float), steps) * STEP_S
    out = np.zeros((S, H, N))
    ages = np.arange(A)
    for i0 in range(0, T, chunk):
        i = np.arange(i0, min(i0 + chunk, T))
        j = i[:, None] + ages[None, :]                      # [n, A] step at which the puff is evaluated
        live = j < T
        jj = np.minimum(j, T - 1)
        ox = cx[j] - cx[i][:, None]; oy = cy[j] - cy[i][:, None]; dist = cp[j] - cp[i][:, None]
        px = src.x[None, None, :] + ox[:, :, None]          # [n, A, S] puff position at the start of step j
        py = src.y[None, None, :] + oy[:, :, None]
        # retired once it leaves the forecast box plus 2 km (checked after each advance, as in simulate)
        ex_j, ey_j, L_j, u_j = ex[jj], ey[jj], L[jj], u[jj]
        nx_ = px + (ex_j * L_j)[:, :, None]; ny_ = py + (ey_j * L_j)[:, :, None]
        gone = np.maximum.accumulate((np.abs(nx_) >= RETIRE_M) | (np.abs(ny_) >= RETIRE_M), axis=1)
        alive = live[:, :, None] & ~np.concatenate([np.zeros_like(gone[:, :1]), gone[:, :-1]], axis=1)
        dx = rx[None, None, None, :] - px[..., None]        # [n, A, S, N]
        dy = ry[None, None, None, :] - py[..., None]
        e_x, e_y = ex_j[:, :, None, None], ey_j[:, :, None, None]
        Lj, uj = L_j[:, :, None, None], u_j[:, :, None, None]
        a = dx * e_x + dy * e_y
        n = -dx * e_y + dy * e_x
        ac = np.clip(a, 0.0, Lj)
        s_r = dist[:, :, None, None] + ac
        cj = np.broadcast_to(cls[jj][:, :, None, None], s_r.shape)
        sy_pg = np.empty_like(s_r); sz_pg = np.empty_like(s_r)
        for c in range(6):
            m = cj == c
            if m.any():
                sy_pg[m] = sigma_y(s_r[m], c); sz_pg[m] = sigma_z(s_r[m], c)
        sy2 = src.sigma_y0 ** 2 + sy_pg ** 2
        if src.sigma_v > 0:
            sy2 = sy2 + (src.sigma_v * (ages[None, :, None, None] * STEP_S + ac / uj)) ** 2
        sy = np.sqrt(sy2)
        sz = np.sqrt(src.sigma_z0 ** 2 + sz_pg ** 2)
        along = (sy / uj) * math.sqrt(math.pi / 2) * (erf(a / (sy * SQRT2)) - erf((a - Lj) / (sy * SQRT2)))
        dose = (mass[i][:, None, None, None] * 2.0 * np.exp(-z * z / (2 * sz * sz)) / (NORM * sy2 * sz)
                * np.exp(-n * n / (2 * sy2)) * along)
        dose = np.where(alive[..., None], dose, 0.0)
        hj = (jj // steps).ravel()
        flat = dose.reshape(-1, S, N)
        for s in range(S):
            for r in range(N):
                out[s, :, r] += np.bincount(hj, weights=flat[:, s, r], minlength=H)
    return ug_m3_to_ppb(out / 3600.0 * 1e6).astype(np.float32)
