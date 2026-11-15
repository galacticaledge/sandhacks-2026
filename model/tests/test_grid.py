"""The forecast box: runs remember their own grid, and puffs live as far as the box reaches."""
from config import BBOX
from model.geo import grid_from_meta, make_grid, retire_m, to_xy

OLD = {"lat_min": 32.535, "lat_max": 32.600, "lon_min": -117.140, "lon_max": -117.030}   # the original 7 x 10 km box


def test_old_run_rebuilds_its_own_50m_grid():
    old = make_grid(50.0, OLD)
    g = grid_from_meta({"bounds": old.bounds, "shape": list(old.shape), "cell_m": 50})
    assert g.shape == old.shape == (144, 206)
    assert g.index_of(32.567, -117.090) == old.index_of(32.567, -117.090)
    assert g.index_of(32.70, -117.16) is None          # downtown was outside the old box


def test_current_box_reaches_downtown_and_chula_vista():
    g = make_grid()
    assert g.index_of(32.7157, -117.1611) is not None  # downtown San Diego
    assert g.index_of(32.6401, -117.0842) is not None  # Chula Vista
    assert g.index_of(32.6859, -117.1831) is not None  # Coronado


def test_puffs_are_kept_until_they_leave_the_whole_box():
    corners = [to_xy(BBOX[a], BBOX[b]) for a in ("lat_min", "lat_max") for b in ("lon_min", "lon_max")]
    far = max(max(abs(x), abs(y)) for x, y in corners)
    assert retire_m() > far


def test_shape_mismatch_is_an_error_not_a_misdrawn_map():
    old = make_grid(50.0, OLD)
    try:
        grid_from_meta({"bounds": old.bounds, "shape": [10, 10], "cell_m": 50})
    except ValueError:
        return
    raise AssertionError("expected ValueError")
