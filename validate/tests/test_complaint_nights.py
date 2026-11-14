from datetime import date, datetime

from config import TZ
from validate import replay

NESTOR = (32.567, -117.090)  # inside the grid
FAR = (32.70, -117.16)  # San Diego downtown, outside the grid


def complaint(y, m, d, hh, where=NESTOR):
    return {"received_at": datetime(y, m, d, hh, tzinfo=TZ), "lat": where[0], "lon": where[1]}


def test_complaint_maps_to_the_5pm_run_whose_window_contains_it(monkeypatch):
    rows = [complaint(2026, 10, 30, 10),   # 10 AM -> previous evening's run (Oct 29, 5 PM)
            complaint(2026, 10, 30, 20),   # 8 PM -> same evening's run (Oct 30, 5 PM)
            complaint(2026, 10, 30, 17),   # exactly 5 PM -> that evening's run
            complaint(2026, 10, 25, 9, FAR)]  # outside the forecast grid -> ignored
    monkeypatch.setattr(replay.store, "complaints", lambda a, b: rows)
    assert replay.complaint_nights(now=datetime(2026, 11, 1, tzinfo=TZ)) == [date(2026, 10, 30), date(2026, 10, 29)]


def test_window_offset_is_within_24h(monkeypatch):
    c = complaint(2026, 10, 30, 10)
    monkeypatch.setattr(replay.store, "complaints", lambda a, b: [c])
    night = replay.complaint_nights(now=datetime(2026, 11, 1, tzinfo=TZ))[0]
    h = (c["received_at"] - replay.issue_time(night)).total_seconds() / 3600
    assert 0 <= h < 24
