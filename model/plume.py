"""Steady-state Gaussian plume per hour (spec 5.3 fallback). Same stability classes as the puff model."""
from __future__ import annotations

import math

import numpy as np

from model.emission import ug_m3_to_ppb
from model.met import WIND_FLOOR_MS, Met
from model.sources import SourceConfig
from model.stability import sigma_y, sigma_z


def simulate(met: Met, emis_gps: np.ndarray, src: SourceConfig, rx, ry, z: float = 1.5) -> np.ndarray:
    rx = np.asarray(rx, dtype=np.float32)
    ry = np.asarray(ry, dtype=np.float32)
    out = np.zeros((len(met), rx.size), dtype=np.float32)
    for h in range(len(met)):
        u = max(float(met.wind_ms[h]), WIND_FLOOR_MS)
        th = math.radians(float(met.wind_dir_deg[h]))
        ex, ey = -math.sin(th), -math.cos(th)
        cls = int(met.stab[h])
        for s in range(len(src.ids)):
            q = float(emis_gps[h]) * src.shares[s]
            dx, dy = rx - src.x[s], ry - src.y[s]
            xd = dx * ex + dy * ey
            yc = -dx * ey + dy * ex
            ok = xd > 1.0
            sy = np.sqrt(src.sigma_y0 ** 2 + sigma_y(np.where(ok, xd, 1.0), cls) ** 2)
            sz = np.sqrt(src.sigma_z0 ** 2 + sigma_z(np.where(ok, xd, 1.0), cls) ** 2)
            c = q / (2 * math.pi * u * sy * sz) * np.exp(-yc ** 2 / (2 * sy ** 2)) * 2 * np.exp(-z * z / (2 * sz ** 2))
            out[h] += np.where(ok, c, 0.0)
    return ug_m3_to_ppb(out * 1e6).astype(np.float32)
