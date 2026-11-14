import json

from collectors import h2s_feed, nws, powerbi_history


def test_h2s_parse_handles_missing_level_and_negative():
    payload = json.dumps({"data": [
        {"SiteName": "SAN YSIDRO", "Date with time": "2026-11-14T11:00:00-08:00", "Result": -0.1, "Qualifier": ""},
        {"SiteName": "NESTOR - BES", "Date with time": "2026-11-14T11:00:00-08:00", "Result": 31.0, "Qualifier": "", "level": "orange"},
        {"SiteName": "UNKNOWN", "Date with time": "2026-11-14T11:00:00-08:00", "Result": 1}]}).encode()
    rows = h2s_feed.parse(payload)
    assert len(rows) == 2
    assert rows[0]["level"] == "green" and rows[1]["level"] == "orange"
    assert rows[0]["observed_at"].isoformat() == "2026-11-14T19:00:00+00:00"


def test_nws_duration():
    assert nws._duration_hours("PT3H") == 3
    assert nws._duration_hours("P1DT2H") == 26


def test_powerbi_dsr_decode_with_repeats_and_dicts():
    res = {"result": {"data": {
        "descriptor": {"Select": [{"Value": "G0", "Name": "Sharepoint-Data.DATETIME"},
                                  {"Value": "G1", "Name": "Sharepoint-Data.Location"},
                                  {"Value": "M0", "Name": "Sum(Sharepoint-Data.ppB)"}]},
        "dsr": {"DS": [{"ValueDicts": {"D0": ["Nestor - BES", "San Ysidro"]}, "PH": [{"DM0": [
            {"S": [{"N": "G0", "T": 7}, {"N": "G1", "T": 1, "DN": "D0"}, {"N": "M0", "T": 3}], "C": [1773100800000, 0, 12.5]},
            {"C": [1, 3.0], "R": 1},
            {"C": [1773104400000], "R": 2, "Ø": 4},
        ]}]}]}}}}
    rows = powerbi_history.decode_dsr(res)
    assert rows[1]["Sharepoint-Data.Location"] == "San Ysidro" and rows[1]["Sharepoint-Data.DATETIME"] == 1773100800000
    assert rows[2]["Sum(Sharepoint-Data.ppB)"] is None and rows[2]["Sharepoint-Data.Location"] == "San Ysidro"
    rd = powerbi_history.to_readings(rows)
    assert rd[0]["site_id"] == "nestor_bes" and rd[0]["level"] == "yellow"
