"""What the Accuracy page is allowed to count: replays from the current calibration, complaints with a real location."""
from validate import replay

CAL = {"log_k": -6.0, "alpha": 0.98, "shares": [0.7, 0.2, 0.1], "fitted_at": "2026-11-14T21:00:00+00:00",
       "window": ["2023-12-31", "2026-01-01"]}


def test_refit_with_same_parameters_keeps_cached_replays():
    again = {**CAL, "fitted_at": "2026-11-15T11:30:00+00:00"}
    assert replay.calibration_key(again) == replay.calibration_key(CAL)


def test_changed_parameters_make_cached_replays_stale():
    meta = {"inputs": {"calibration": CAL}}
    assert replay.is_current(meta, replay.calibration_key(CAL))
    assert not replay.is_current(meta, replay.calibration_key({**CAL, "alpha": 1.1}))


def test_replay_without_calibration_is_not_current_once_one_exists():
    old = {"inputs": {"calibration": {"note": "prior only (not enough history before this night)"}}}
    assert not replay.is_current(old, replay.calibration_key(CAL))
    assert not replay.is_current({"inputs": {}}, replay.calibration_key(CAL))


def test_point_used_under_several_city_names_is_a_placeholder():
    rows = [{"lat": 32.55201, "lon": -117.08131, "city": "Imperial Beach"},
            {"lat": 32.55201, "lon": -117.08131, "city": "Chula Vista"},
            {"lat": 32.5448, "lon": -117.0843, "city": "Imperial Beach"},   # one household calling often: real
            {"lat": 32.5448, "lon": -117.0843, "city": "imperial beach "},  # same city, other spelling
            {"lat": 32.5791, "lon": -117.1057, "city": None}]
    assert replay.placeholder_points(rows) == {(32.552, -117.0813)}
