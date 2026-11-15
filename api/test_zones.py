import numpy as np

from api.zones import zones_from_grid

LONS = np.linspace(-117.14, -117.03, 60)
LATS = np.linspace(32.60, 32.535, 50)  # north to south, like the model grid


def plume(peak: float, ci: int = 25, cj: int = 30, width: float = 6.0) -> np.ndarray:
    i, j = np.mgrid[0:50, 0:60]
    return peak * np.exp(-(((i - ci) / width) ** 2 + ((j - cj) / width) ** 2))


def inside(pt, ring) -> bool:
    x, y = pt
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def levels(fc):
    return [f["properties"]["level"] for f in fc["features"]]


def test_bands_follow_the_peak():
    fc = zones_from_grid(plume(100.0), LONS, LATS)
    assert levels(fc) == ["green", "yellow", "orange"]  # peak 100 ppb never reaches the 200 ppb band


def test_all_four_bands_when_peak_is_high():
    assert levels(zones_from_grid(plume(500.0), LONS, LATS)) == ["green", "yellow", "orange", "review"]


def test_flat_low_grid_has_no_zones():
    assert zones_from_grid(np.full((50, 60), 0.5), LONS, LATS)["features"] == []


def test_nan_cells_are_treated_as_zero():
    z = plume(50.0)
    z[0:5, 0:5] = np.nan
    assert levels(zones_from_grid(z, LONS, LATS)) == ["green", "yellow", "orange"]


def test_zone_contains_the_peak_and_stays_in_the_grid():
    fc = zones_from_grid(plume(100.0), LONS, LATS)
    orange = next(f for f in fc["features"] if f["properties"]["level"] == "orange")
    peak = (float(LONS[30]), float(LATS[25]))
    assert any(inside(peak, poly[0]) for poly in orange["geometry"]["coordinates"])
    for f in fc["features"]:
        for poly in f["geometry"]["coordinates"]:
            for ring in poly:
                assert ring[0] == ring[-1]
                xs, ys = zip(*ring)
                assert LONS.min() - 1e-6 <= min(xs) and max(xs) <= LONS.max() + 1e-6
                assert LATS.min() - 1e-6 <= min(ys) and max(ys) <= LATS.max() + 1e-6


def test_lower_band_is_a_ring_around_the_higher_one():
    # the 5-30 ppb zone must have a hole where concentrations exceed 30 ppb
    fc = zones_from_grid(plume(100.0), LONS, LATS)
    yellow = next(f for f in fc["features"] if f["properties"]["level"] == "yellow")
    assert any(len(poly) >= 2 for poly in yellow["geometry"]["coordinates"])
    assert yellow["properties"] == {"level": "yellow", "min_ppb": 5.0, "max_ppb": 30.0}
