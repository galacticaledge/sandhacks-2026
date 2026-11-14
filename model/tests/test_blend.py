import numpy as np
import pytest

from model import blend


def _nights(n=400, M=3, seed=0):
    rng = np.random.default_rng(seed)
    X = np.empty((n, M, 3 * M + 2))
    for k in range(n):
        hist = {"last_night": rng.uniform(0, 5, M), "week": rng.uniform(0, 5, M), "today": rng.uniform(0, 2, M)}
        X[k] = blend.design(np.expm1(rng.uniform(0, 5, M)), hist)
    return X, rng


def test_fit_recovers_coefficients_and_quantiles_are_ordered():
    X, rng = _nights()
    coef = np.array([0.2, 0.4, 0.6, 0.8, 0.6, 0.5, 0.1, 0.2, 0.3, 0.2, 0.1])
    y = X @ coef + rng.normal(0, 0.3, X.shape[:2])
    b = blend.fit(X, np.expm1(y))
    np.testing.assert_allclose(b["coef"], coef, atol=0.1)
    q = blend.predict(b, X)
    assert q.shape == X.shape[:2] + (3,)
    assert np.all(q[..., 0] <= q[..., 1]) and np.all(q[..., 1] <= q[..., 2])
    under = (np.expm1(y) <= q[..., 2]).mean()
    assert under == pytest.approx(0.9, abs=0.03)   # P90 holds about 90 % of nights


def test_fit_ignores_masked_monitor():
    X, rng = _nights()
    y = X @ np.linspace(0.1, 0.5, X.shape[2]) + rng.normal(0, 0.2, X.shape[:2])
    use = np.ones(y.shape, bool); use[:, 1] = False
    y_bad = y.copy(); y_bad[:, 1] = 99.0   # garbage at the masked monitor must not matter
    a = blend.fit(X, np.expm1(y), use); b = blend.fit(X, np.expm1(y_bad), use)
    np.testing.assert_allclose(a["coef"], b["coef"])


def test_history_features_fall_back_when_readings_are_missing():
    prev = np.full((blend.WEEK_N, 2), np.nan)
    prev[1, 0] = np.expm1(3.0)                      # monitor 0: last night missing, one older night known
    f = blend.history_features(prev, np.full((8, 2), np.nan), base=np.array([1.0, 2.0]))
    assert f["last_night"][0] == pytest.approx(3.0) and f["week"][0] == pytest.approx(3.0)
    assert f["last_night"][1] == pytest.approx(2.0)  # nothing known: the monitor's usual level
    assert np.all(f["today"] == blend.TODAY_FILL)


def test_night_peak_needs_six_readings():
    v = np.full((15, 2), np.nan); v[:5, 0] = 40.0; v[:6, 1] = [1, 2, 50, 3, 4, 5]
    p = blend.night_peak(v)
    assert np.isnan(p[0]) and p[1] == 50.0


def test_scales_reproduce_the_quantiles_and_spread_smoothly():
    q = np.array([[5.0, 20.0, 80.0], [10.0, 40.0, 100.0]])
    peak = np.array([10.0, 10.0])
    sc = blend.scales(q, peak)
    np.testing.assert_allclose(sc * peak[:, None], q)
    mx, my = np.array([0.0, 1000.0]), np.array([0.0, 0.0])
    s = blend.spread_scales(sc, mx, my, np.array([0.0, 500.0, 1000.0]), np.array([0.0, 0.0, 0.0]))
    np.testing.assert_allclose(s[0], sc[0], rtol=1e-4)          # on a monitor: that monitor's scale
    np.testing.assert_allclose(s[2], sc[1], rtol=1e-4)
    np.testing.assert_allclose(s[1], np.sqrt(sc[0] * sc[1]))    # halfway: geometric mean
    only0 = blend.spread_scales(sc, mx, my, np.array([900.0]), np.array([0.0]), use=np.array([True, False]))
    np.testing.assert_allclose(only0[0], sc[0])                 # leave-one-out: the masked monitor is not used


def test_night_window_matches_alerts():
    assert [h for h in range(24) if blend.is_night_hour(h)] == list(range(9)) + list(range(18, 24))
