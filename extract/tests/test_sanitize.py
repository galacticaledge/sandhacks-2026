"""sanitize() cases taken from real Gemini mistakes on USIBWC releases (2026-11-14)."""
from extract.gemini_events import FlowEvent, sanitize

STORM = ("The Tijuana River is estimated to be flowing at 64 Million Gallons per Day (MGD) as of 12pm PDT "
         "which will fluctuate and peak above 190 MGD during this rain event.")
PLANT = ("Repairs to the South Bay International Wastewater Treatment Plant's (SBIWTP) advanced primary chemical "
         "treatment system have been completed, and the plant is ready to resume treating up to 35 million gallons "
         "per day (MGD).")
PUMP = ("The Comision Internacional de Limites y Aguas (CILA) notified USIBWC that the Tijuana sanitation utility shut "
        "down Mexican pump PB1 Wednesday 04/08 from 9:00pm - Thursday 04/09 4:45am PDT to remove large amounts of "
        "sediment as part of maintenance.")


def ev(quote, subject, **nums):
    return FlowEvent(published_at="2026-05-05T12:00:00-07:00", event_type="storm", location_text="border",
                     starts_at="2026-05-05T12:00:00-07:00", flow_subject=subject, confidence=0.9, quote=quote, **nums)


def test_river_flow_stated_in_quote_is_kept():
    e = sanitize(ev(STORM, "river_at_border", expected_flow_mgd=64, peak_flow_mgd=190), STORM)
    assert (e.expected_flow_mgd, e.peak_flow_mgd, e.confidence) == (64, 190, 0.9)


def test_treatment_plant_capacity_is_not_river_flow():
    e = sanitize(ev(PLANT, "treatment_plant", expected_flow_mgd=35), PLANT)
    assert e.expected_flow_mgd is None
    assert e.confidence == 0.9  # event stays on the timeline


def test_plant_number_mislabelled_as_river_still_dropped_if_not_in_quote():
    e = sanitize(ev(PLANT, "river_at_border", expected_flow_mgd=25, flow_delta_mgd=-10), PLANT)
    assert e.expected_flow_mgd is None and e.flow_delta_mgd is None


def test_number_absent_from_quote_is_dropped():
    e = sanitize(ev(PUMP, "river_at_border", peak_flow_mgd=42.5), PUMP)
    assert e.peak_flow_mgd is None


def test_only_the_unsupported_river_number_is_dropped():
    q = "With 2 PBCILA pumps online, Tijuana River flow has reduced to 8.36 MGD."
    e = sanitize(ev(q, "river_at_border", expected_flow_mgd=8.36, peak_flow_mgd=42.5), q)
    assert (e.expected_flow_mgd, e.peak_flow_mgd) == (8.36, None)


def test_negative_delta_matches_unsigned_number_in_quote():
    q = "Transboundary flows into the Tijuana River are expected to drop by 10 MGD."
    e = sanitize(ev(q, "river_at_border", flow_delta_mgd=-10), q)
    assert e.flow_delta_mgd == -10


def test_quote_not_in_source_caps_confidence():
    e = sanitize(ev(STORM, "river_at_border", expected_flow_mgd=64), "some other document text")
    assert e.confidence == 0.5
