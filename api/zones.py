"""Predicted concentration zones: filled contours of the model's own H2S grid, as GeoJSON.

The shapes are traced straight from the forecast grid (p50 or p90, one hour) at SDAPCD thresholds.
Nothing is smoothed, buffered or drawn around monitors; a zone exists only where the model predicts it.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from contourpy import FillType, contour_generator

from model.geo import make_grid

# (level key, lower ppb, upper ppb). Upper None = no ceiling. "green" starts at 1 ppb so the whole
# basin is not painted; below 1 ppb the overlay PNG is transparent too (model/render.py).
BANDS = [("green", 1.0, 5.0), ("yellow", 5.0, 30.0), ("orange", 30.0, 200.0), ("review", 200.0, None)]
CEILING = 1e9  # stands in for "no upper bound" in contourpy


def _ring(points: np.ndarray, nd: int = 5) -> list[list[float]]:
    ring = [[round(float(x), nd), round(float(y), nd)] for x, y in points]
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def zones_from_grid(ppb: np.ndarray, lons: np.ndarray, lats: np.ndarray) -> dict:
    """ppb: 2-D (ny, nx) grid with rows ordered like `lats` (north to south). Returns a FeatureCollection."""
    z = np.nan_to_num(np.asarray(ppb, dtype=np.float64), nan=0.0)
    gen = contour_generator(x=lons, y=lats, z=z, fill_type=FillType.OuterOffset)
    feats = []
    for key, lo, hi in BANDS:
        if z.max() < lo:
            continue
        polys = []
        points, offsets = gen.filled(lo, hi if hi is not None else CEILING)
        for pts, off in zip(points, offsets):
            rings = [_ring(pts[off[k]:off[k + 1]]) for k in range(len(off) - 1)]
            rings = [r for r in rings if len(r) >= 4]
            if rings:
                polys.append(rings)  # first ring = outer boundary, the rest are holes
        if polys:
            feats.append({
                "type": "Feature",
                "properties": {"level": key, "min_ppb": lo, "max_ppb": hi},
                "geometry": {"type": "MultiPolygon", "coordinates": polys},
            })
    return {"type": "FeatureCollection", "features": feats}


@lru_cache(maxsize=1)
def _axes():
    g = make_grid()
    return np.asarray(g.lons, dtype=np.float64), np.asarray(g.lats, dtype=np.float64)


@lru_cache(maxsize=96)
def zones_for(run_id: str, hour: int, pct: str) -> dict:
    from api.runs import _grid_arrays  # local import: keeps this module importable in tests without run files
    lons, lats = _axes()
    return zones_from_grid(_grid_arrays(run_id)[pct][hour], lons, lats)
