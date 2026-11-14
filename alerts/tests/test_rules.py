from datetime import datetime, timedelta

from alerts.rules import evaluate, night_window
from config import TZ


def times():
    t0 = datetime(2026, 11, 14, 17, tzinfo=TZ)
    return [t0 + timedelta(hours=i) for i in range(24)]


def test_night_window_is_6pm_to_9am():
    w = night_window(times())
    assert times()[w[0]].hour == 18 and times()[w[-1]].hour == 8 and len(w) == 15


def test_likely_possible_none():
    t = times()
    base = [1.0] * 24
    p50 = list(base); p50[8] = 45  # 1 AM
    r = evaluate(t, base, p50, [x * 2 for x in p50])
    assert r["kind"] == "likely" and r["level"] == "orange"
    p90 = list(base); p90[8] = 40
    r = evaluate(t, base, base, p90)
    assert r["kind"] == "possible" and r["confidence"] == "low"
    assert evaluate(t, base, base, base)["kind"] == "none"


def test_daytime_peak_ignored():
    t = times()
    p = [1.0] * 24; p[20] = 80  # 1 PM next day
    assert evaluate(t, p, p, p)["kind"] == "none"
