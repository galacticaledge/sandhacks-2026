"""Local tangent-plane coordinates and the 50 m forecast grid."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from config import BBOX, GRID_M, REF_LAT, REF_LON

M_PER_DEG_LAT = 110_950.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(REF_LAT))


def to_xy(lat, lon):
    lat = np.asarray(lat, dtype=np.float64)
    lon = np.asarray(lon, dtype=np.float64)
    return (lon - REF_LON) * M_PER_DEG_LON, (lat - REF_LAT) * M_PER_DEG_LAT


def to_latlon(x, y):
    return REF_LAT + np.asarray(y) / M_PER_DEG_LAT, REF_LON + np.asarray(x) / M_PER_DEG_LON


@dataclass(frozen=True)
class Grid:
    lats: np.ndarray  # cell-centre latitudes, north -> south (image row order)
    lons: np.ndarray  # cell-centre longitudes, west -> east
    x: np.ndarray     # flattened cell x (m), row-major (ny, nx)
    y: np.ndarray
    bbox: tuple = tuple(BBOX.items())   # this grid's own extent: older runs keep the box they were made with

    @property
    def shape(self):
        return (len(self.lats), len(self.lons))

    @property
    def bounds(self):
        """[[lon,lat] x4] corners for a MapLibre image source: TL, TR, BR, BL."""
        b = dict(self.bbox)
        return [[b["lon_min"], b["lat_max"]], [b["lon_max"], b["lat_max"]],
                [b["lon_max"], b["lat_min"]], [b["lon_min"], b["lat_min"]]]

    def index_of(self, lat: float, lon: float) -> tuple[int, int] | None:
        b = dict(self.bbox)
        if not (b["lat_min"] <= lat <= b["lat_max"] and b["lon_min"] <= lon <= b["lon_max"]):
            return None
        i = int(np.argmin(np.abs(self.lats - lat)))
        j = int(np.argmin(np.abs(self.lons - lon)))
        return i, j


def make_grid(cell_m: float = GRID_M, bbox: dict | None = None) -> Grid:
    b = bbox or BBOX
    dlat = cell_m / M_PER_DEG_LAT
    dlon = cell_m / M_PER_DEG_LON
    ny = int(round((b["lat_max"] - b["lat_min"]) / dlat))
    nx = int(round((b["lon_max"] - b["lon_min"]) / dlon))
    lats = np.linspace(b["lat_max"] - dlat / 2, b["lat_min"] + dlat / 2, ny)
    lons = np.linspace(b["lon_min"] + dlon / 2, b["lon_max"] - dlon / 2, nx)
    LON, LAT = np.meshgrid(lons, lats)
    x, y = to_xy(LAT.ravel(), LON.ravel())
    return Grid(lats=lats, lons=lons, x=x.astype(np.float32), y=y.astype(np.float32), bbox=tuple(b.items()))


def grid_from_meta(g: dict) -> Grid:
    """Rebuild the grid a run was made with, from its meta["grid"] (bounds TL, TR, BR, BL as [lon, lat], cell_m)."""
    (w, n), _, (e, s), _ = g["bounds"]
    grid = make_grid(float(g.get("cell_m") or 50), {"lat_min": s, "lat_max": n, "lon_min": w, "lon_max": e})
    if list(grid.shape) != list(g["shape"]):
        raise ValueError(f"grid shape {grid.shape} does not match the run's {g['shape']}")
    return grid


def retire_m(margin_m: float = 2000.0) -> float:
    """Puffs farther than this from the origin (either axis) are dropped: the forecast box plus a margin."""
    b = BBOX
    x0, y0 = to_xy(b["lat_min"], b["lon_min"]); x1, y1 = to_xy(b["lat_max"], b["lon_max"])
    return float(max(abs(x0), abs(x1), abs(y0), abs(y1)) + margin_m)
