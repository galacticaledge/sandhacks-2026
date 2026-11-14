from alerts.send import render


def ev(kind):
    return {"kind": kind, "peak_p50": 42.0, "peak_p90": 90.0, "peak_p10": 10.0, "confidence": "medium",
            "level": "orange", "level_p90": "orange", "window": ["2026-11-14T18:00:00-08:00", "2026-11-15T08:00:00-08:00"],
            "orange_window": ["2026-11-15T01:00:00-08:00", "2026-11-15T05:00:00-08:00"]}


def test_render_en_includes_required_parts():
    subj, body = render("en", "Nestor", ev("likely"), "https://x/api/unsubscribe/t")
    assert "LIKELY ORANGE" in subj
    for part in ("1 AM - 5 AM", "Keep doors and windows closed", "EXPERIMENTAL FORECAST, NOT AN OFFICIAL ADVISORY",
                 "sdapcd.org", "unsubscribe/t", "Confidence: medium"):
        assert part in body


def test_render_es_possible():
    subj, body = render("es", "San Ysidro", ev("possible"), "u")
    assert "POSIBLE NARANJA" in subj and "Mantenga cerradas puertas y ventanas" in body and "NO ES UN AVISO OFICIAL" in body


def test_likely_at_200ppb_uses_review_guidance_but_possible_never_does():
    from alerts.guidance import GUIDANCE
    hi = {**ev("likely"), "peak_p50": 240.0, "level": "review", "level_p90": "review"}
    assert GUIDANCE["en"]["review"]["expect"] in render("en", "Nestor", hi, "u")[1]
    poss = {**ev("possible"), "peak_p50": 22.0, "peak_p90": 250.0, "level": "yellow", "level_p90": "review"}
    body = render("en", "Nestor", poss, "u")[1]
    assert GUIDANCE["en"]["orange"]["expect"] in body and GUIDANCE["en"]["review"]["expect"] not in body
