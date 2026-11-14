"""Parser test for collectors/h2s_history.py on a tiny sample of real rows from the Resilient Shield CSVs."""
from datetime import date, datetime, timezone
from pathlib import Path

from collectors import h2s_history

SAMPLE = Path(__file__).parent / "data" / "resilient_h2s_history_sample.csv"
UTC = timezone.utc


def _rows():
    return h2s_history.parse(SAMPLE.read_bytes())


def test_parse_sites_units_and_source():
    rows = _rows()
    assert len(rows) == 9
    assert {r["site_id"] for r in rows} == {"ib_civic", "nestor_bes", "san_ysidro"}
    assert {r["source"] for r in rows} == {"resilient_history"}
    assert all(r["observed_at"].tzinfo is not None and r["observed_at"].utcoffset().total_seconds() == 0 for r in rows)
    by = {(r["site_id"], r["observed_at"]): r for r in rows}
    # summer row: 01:00 PDT = 08:00 UTC (= 00:00 Pacific Standard Time, the hour SDAPCD reports this value under)
    peak = by[("nestor_bes", datetime(2026, 6, 2, 8, tzinfo=UTC))]
    assert peak["ppb"] == 915.0 and peak["level"] == "review"
    # winter row: 05:00 PST = 13:00 UTC
    assert by[("san_ysidro", datetime(2025, 1, 15, 13, tzinfo=UTC))]["level"] == "green"
    assert by[("ib_civic", datetime(2025, 4, 21, 10, tzinfo=UTC))]["ppb"] == 264.0


def test_parse_qualifier_and_negative():
    by = {(r["site_id"], r["observed_at"]): r for r in _rows()}
    flagged = by[("san_ysidro", datetime(2025, 10, 9, 17, tzinfo=UTC))]  # Qualifier '<', blank Result
    assert flagged["ppb"] is None and flagged["level"] is None
    neg = by[("san_ysidro", datetime(2024, 9, 15, 16, tzinfo=UTC))]  # raw -0.3 with a blank level
    assert neg["ppb"] == -0.3 and neg["level"] == "green"


def test_same_wall_clock_two_offsets_are_two_hours():
    """The files label 2025-11-03 00:00 twice (-07:00 and -08:00). They are consecutive hours, not duplicates."""
    times = sorted(r["observed_at"] for r in _rows() if r["site_id"] == "nestor_bes" and r["observed_at"].year == 2025)
    assert times == [datetime(2025, 11, 3, h, tzinfo=UTC) for h in (6, 7, 8, 9)]
    assert len(h2s_history.merge([_rows()])) == 9


def test_merge_later_file_wins_but_null_never_replaces_value():
    t = datetime(2026, 1, 1, 8, tzinfo=UTC)
    old = {"observed_at": t, "site_id": "nestor_bes", "ppb": 4.0, "level": "green", "source": "resilient_history"}
    assert h2s_history.merge([[old], [{**old, "ppb": 6.0, "level": "yellow"}]])[0]["ppb"] == 6.0
    assert h2s_history.merge([[old], [{**old, "ppb": None, "level": None}]])[0]["ppb"] == 4.0


def test_night_of_uses_evening_date():
    assert h2s_history.night_of(datetime(2026, 6, 2, 8, tzinfo=UTC)) == date(2026, 6, 1)    # 1 AM PDT
    assert h2s_history.night_of(datetime(2026, 6, 2, 1, tzinfo=UTC)) == date(2026, 6, 1)    # 6 PM PDT
    assert h2s_history.night_of(datetime(2026, 6, 1, 20, tzinfo=UTC)) is None               # 1 PM PDT
    assert h2s_history.night_of(datetime(2026, 1, 10, 16, tzinfo=UTC)) == date(2026, 1, 9)  # 8 AM PST
    assert h2s_history.night_of(datetime(2026, 1, 10, 17, tzinfo=UTC)) is None              # 9 AM PST


def test_failure_spike_before_outage_is_blanked_but_real_peaks_stay():
    from datetime import datetime, timedelta, timezone
    from collectors.h2s_history import drop_failure_spikes
    t0 = datetime(2024, 9, 1, tzinfo=timezone.utc)
    def row(h, v): return {"site_id": "san_ysidro", "observed_at": t0 + timedelta(hours=h), "ppb": v, "level": "x"}
    rows = [row(0, 0.3), row(1, 19.0), row(2, 703.1), row(2000, 1.0),          # dies after the spike
            row(2001, 35.0), row(2002, 306.0), row(2003, 915.0), row(2004, 133.0)]  # a real episode
    assert drop_failure_spikes(rows) == 1
    assert rows[2]["ppb"] is None and rows[6]["ppb"] == 915.0
