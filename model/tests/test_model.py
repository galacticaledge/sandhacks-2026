from datetime import datetime, timedelta

import numpy as np
import pytest

from config import TZ
from model import calibrate, ensemble, plume, puff
from model.emission import emission_factor, ppb_to_ug_m3, ug_m3_to_ppb
from model.kalman import LogKFilter, relax_toward
from model.met import Met
from model.sources import load_sources
from model.stability import A, B, D, F, sigma_y, stability_classes, sun_elevation_deg, turner_class


def steady_met(hours=8, ws=2.0, wd=180.0, start=datetime(2026, 11, 14, 22, tzinfo=TZ), cloud=0.0, temp=15.0):
    times = [start + timedelta(hours=i) for i in range(hours)]
    return Met(times, np.full(hours, ws), np.full(hours, wd), np.full(hours, temp), np.full(hours, cloud))


def single_source():
    src = load_sources()
    return src.with_params(shares=np.array([1.0, 0.0, 0.0]))


def test_unit_conversion_roundtrip():
    assert ug_m3_to_ppb(34.08) == pytest.approx(24.45)
    assert ppb_to_ug_m3(ug_m3_to_ppb(10.0)) == pytest.approx(10.0)


def test_emission_factor_reference():
    assert emission_factor(10, 15, 1.0, 0.05) == pytest.approx(10.0)
    assert emission_factor(10, 25, 1.0, 0.05) == pytest.approx(10 * np.exp(0.5))


def test_stability_classes():
    noon = datetime(2026, 6, 21, 12, tzinfo=TZ)
    assert sun_elevation_deg(noon) > 70
    assert turner_class(1.0, 75, 0.0) == A
    assert turner_class(1.0, -20, 0.0) == F
    assert turner_class(8.0, -20, 0.0) == D
    assert turner_class(1.0, 75, 1.0) == D
    night = stability_classes([datetime(2026, 11, 14, 2, tzinfo=TZ)], [0.8], [0.1])
    assert night[0] == F


def test_sigma_grows_with_distance_and_instability():
    assert sigma_y(1000, F) < sigma_y(1000, D) < sigma_y(1000, B)
    assert sigma_y(2000, D) > sigma_y(500, D)


def test_puff_upwind_is_zero_and_downwind_positive():
    src = single_source()
    met = steady_met(wd=180)  # wind from the south -> plume goes north
    x0, y0 = src.x[0], src.y[0]
    rx = np.array([x0, x0])
    ry = np.array([y0 + 1500, y0 - 1500])
    c = puff.simulate(met, np.full(len(met), 0.1), src, rx, ry)
    assert c[-1, 0] > 1.0
    assert c[-1, 1] < 1e-6


def test_puff_matches_plume_in_steady_state():
    src = single_source()
    met = steady_met(hours=6, ws=2.0, wd=180)
    x0, y0 = src.x[0], src.y[0]
    rx = np.array([x0] * 3)
    ry = np.array([y0 + 500, y0 + 1000, y0 + 2000])
    e = np.full(len(met), 0.1)
    cp = puff.simulate(met, e, src, rx, ry)[-1]
    cs = plume.simulate(met, e, src, rx, ry)[-1]
    np.testing.assert_allclose(cp, cs, rtol=0.25)


def test_calm_stable_night_is_worse_than_windy_day():
    src = single_source()
    x0, y0 = src.x[0], src.y[0]
    rx, ry = np.array([x0]), np.array([y0 + 1500])
    night = steady_met(ws=0.6, cloud=0.0)
    day = steady_met(ws=6.0, start=datetime(2026, 7, 1, 10, tzinfo=TZ))
    e = np.full(8, 0.1)
    assert puff.simulate(night, e, src, rx, ry)[-1, 0] > 10 * puff.simulate(day, e, src, rx, ry)[-1, 0]


def test_kalman_converges_to_truth():
    f = LogKFilter(mean=-8.0, var=4.0)
    true_logk, unit, bg = -5.0, 2000.0, 0.4
    for _ in range(30):
        f.predict()
        f.update(np.exp(true_logk) * unit + bg, unit, bg)
    assert f.mean == pytest.approx(true_logk, abs=0.1)


def test_kalman_ignores_offaxis_monitor():
    f = LogKFilter(mean=-5.0, var=1.0)
    assert not f.update(80.0, 1e-6, 0.4)
    assert f.mean == -5.0


def test_relaxation():
    r = relax_toward(-4.0, -6.0, np.array([0, 6, 12, 24]))
    np.testing.assert_allclose(r, [-4.0, -5.0, -6.0, -6.0])


def test_calibration_recovers_log_k():
    src = load_sources()
    rng = np.random.default_rng(1)
    hours = 24
    start = datetime(2026, 11, 13, 18, tzinfo=TZ)
    times = [start + timedelta(hours=i) for i in range(hours)]
    met = Met(times, rng.uniform(0.5, 3, hours), rng.uniform(120, 240, hours), np.full(hours, 16.0), np.zeros(hours))
    mx = src.x + np.array([0, 300, 600]); my = src.y + 1200
    flow = np.full(hours, 35.0)
    unit = calibrate.unit_responses(met, src, mx, my)
    truth = src.log_k + 0.7
    f = emission_factor(flow, met.temp_c, src.alpha, src.beta)
    obs = np.exp(truth) * f[:, None] * np.tensordot(src.shares, unit, axes=(0, 0)) + 0.4
    res = calibrate.fit(met, flow, obs, src, mx, my, unit=unit)
    assert res.log_k == pytest.approx(truth, abs=0.3)


def test_ensemble_percentiles_ordered():
    src = load_sources()
    met = steady_met(hours=4, ws=1.0)
    rx = src.x[:1]; ry = src.y[:1] + 1000
    r = ensemble.run(met, np.full(4, 35.0), np.full(4, src.log_k), 0.3, src, rx, ry, 0.4, n=8)
    assert np.all(r.p10 <= r.p50 + 1e-6) and np.all(r.p50 <= r.p90 + 1e-6)
    assert ensemble.confidence_label(10, 12) == "high"
    assert ensemble.confidence_label(10, 60) == "low"


def test_flow_series_uses_each_days_gauge_and_never_the_issue_day(monkeypatch):
    from datetime import datetime, timedelta
    from config import TZ
    from model import inputs
    gauge = {"2026-04-01": 10.0, "2026-04-02": 20.0, "2026-04-03": 999.0}  # 04-03 is the partial issue day
    monkeypatch.setattr(inputs.store, "flow_upto", lambda day, n: [
        {"date": d, "mgd": v} for d, v in sorted(gauge.items(), reverse=True) if d <= day.isoformat()])
    plant = {"id": "e1", "event_type": "repair", "quote": "q", "confidence": 0.9, "published_at": None,
             "starts_at": datetime(2026, 4, 1, tzinfo=TZ), "ends_at": datetime(2026, 4, 9, tzinfo=TZ),
             "expected_flow_mgd": 50.0, "flow_delta_mgd": None}
    monkeypatch.setattr(inputs.store, "flow_events", lambda: [plant])
    as_of = datetime(2026, 4, 3, 17, tzinfo=TZ)
    times = inputs.hours(datetime(2026, 4, 1, 12, tzinfo=TZ), 72)
    q, used, src = inputs.flow_series(times, as_of)
    assert q[0] == 10.0 and q[24] == 20.0          # measured days keep the gauge, the event cannot override them
    assert 999.0 not in q and src == "gauge 2026-04-02"
    assert q[-1] == 50.0 and used                  # only hours after the last gauge day take the event


def test_hours_steps_in_real_time_across_clock_changes():
    from datetime import datetime, timezone
    from config import TZ
    from model.inputs import hours
    for start in (datetime(2026, 10, 31, 17, tzinfo=TZ), datetime(2026, 3, 7, 17, tzinfo=TZ)):
        h = [t.astimezone(timezone.utc) for t in hours(start, 28)]
        assert len(set(h)) == 28 and all((b - a).total_seconds() == 3600 for a, b in zip(h, h[1:]))
