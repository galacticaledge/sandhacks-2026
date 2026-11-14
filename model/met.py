"""Hourly meteorology container used by every model component."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from model.stability import stability_classes

WIND_FLOOR_MS = 0.5


@dataclass
class Met:
    times: list[datetime]      # tz-aware hour starts
    wind_ms: np.ndarray         # m/s
    wind_dir_deg: np.ndarray    # meteorological "from" direction
    temp_c: np.ndarray
    cloud_frac: np.ndarray      # 0..1
    source: str = "unknown"
    stab: np.ndarray = field(default=None)  # 0..5 = A..F

    def __post_init__(self):
        self.wind_ms = np.maximum(np.asarray(self.wind_ms, dtype=float), 0.0)
        self.wind_dir_deg = np.asarray(self.wind_dir_deg, dtype=float) % 360
        self.temp_c = np.asarray(self.temp_c, dtype=float)
        self.cloud_frac = np.clip(np.asarray(self.cloud_frac, dtype=float), 0, 1)
        if self.stab is None:
            self.stab = stability_classes(self.times, self.wind_ms, self.cloud_frac)

    def __len__(self):
        return len(self.times)

    def perturbed(self, ddir_deg: float, speed_factor: float) -> "Met":
        return Met(self.times, self.wind_ms * speed_factor, self.wind_dir_deg + ddir_deg,
                   self.temp_c, self.cloud_frac, self.source + "+pert")

    def slice(self, a: int, b: int) -> "Met":
        return Met(self.times[a:b], self.wind_ms[a:b], self.wind_dir_deg[a:b], self.temp_c[a:b],
                   self.cloud_frac[a:b], self.source, self.stab[a:b])

    def to_dict(self):
        return {
            "times": [t.isoformat() for t in self.times],
            "wind_ms": np.round(self.wind_ms, 2).tolist(),
            "wind_dir_deg": np.round(self.wind_dir_deg, 0).tolist(),
            "temp_c": np.round(self.temp_c, 1).tolist(),
            "cloud_frac": np.round(self.cloud_frac, 2).tolist(),
            "stability": ["ABCDEF"[int(s)] for s in self.stab],
            "source": self.source,
        }
