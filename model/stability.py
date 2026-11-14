"""Pasquill-Gifford stability (simplified Turner method) and Briggs rural sigma curves."""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np

LAT, LON = 32.5675, -117.085
A, B, C, D, E, F = range(6)


def sun_elevation_deg(t: datetime, lat: float = LAT, lon: float = LON) -> float:
    """NOAA approximate solar elevation for a tz-aware datetime (evaluated mid-hour by callers)."""
    t = t.astimezone(timezone.utc)
    doy = t.timetuple().tm_yday
    hour = t.hour + t.minute / 60
    g = 2 * math.pi / 365 * (doy - 1 + (hour - 12) / 24)
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    tst = hour * 60 + eqt + 4 * lon
    ha = math.radians(tst / 4 - 180)
    la = math.radians(lat)
    cos_z = math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(ha)
    return 90 - math.degrees(math.acos(max(-1.0, min(1.0, cos_z))))


def turner_class(wind_ms: float, sun_elev: float, cloud: float) -> int:
    """Simplified Turner: insolation from sun elevation + cloud, night from cloud cover.
    Half classes (A-B etc.) round to the more stable class."""
    u = wind_ms
    if cloud >= 0.95:
        return D  # overcast, day or night
    if sun_elev > 0:
        ins = 3 if sun_elev > 60 else 2 if sun_elev > 35 else 1 if sun_elev > 15 else 0
        if cloud > 0.5:
            ins = max(ins - 1, 0)
        if ins == 0:
            return D
        table = {  # wind band -> (strong, moderate, slight)
            0: (A, B, B), 1: (B, B, C), 2: (B, C, C), 3: (C, D, D), 4: (C, D, D)}
        band = 0 if u < 2 else 1 if u < 3 else 2 if u < 5 else 3 if u < 6 else 4
        return table[band][3 - ins]
    # night
    cloudy = cloud >= 0.5
    if u < 2:
        return E if cloudy else F
    if u < 3:
        return E if cloudy else F
    if u < 5:
        return D if cloudy else E
    return D


def stability_classes(times, wind_ms, cloud_frac) -> np.ndarray:
    from datetime import timedelta
    out = np.empty(len(times), dtype=np.int8)
    for i, t in enumerate(times):
        elev = sun_elevation_deg(t + timedelta(minutes=30))
        out[i] = turner_class(float(wind_ms[i]), elev, float(cloud_frac[i]))
    return out


# Briggs (1973) open-country sigma formulas, x in metres
_SY = np.array([0.22, 0.16, 0.11, 0.08, 0.06, 0.04])
_SZ = [
    lambda x: 0.20 * x,
    lambda x: 0.12 * x,
    lambda x: 0.08 * x / np.sqrt(1 + 0.0002 * x),
    lambda x: 0.06 * x / np.sqrt(1 + 0.0015 * x),
    lambda x: 0.03 * x / (1 + 0.0003 * x),
    lambda x: 0.016 * x / (1 + 0.0003 * x),
]


def sigma_y(x, cls: int):
    x = np.maximum(np.asarray(x, dtype=np.float32), 1.0)
    return _SY[cls] * x / np.sqrt(1 + 0.0001 * x)


def sigma_z(x, cls: int):
    x = np.maximum(np.asarray(x, dtype=np.float32), 1.0)
    return np.minimum(_SZ[cls](x), 1000.0)
