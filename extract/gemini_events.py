"""Gemini turns commission announcements into structured flow events (spec 6). It never produces a concentration."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger("gemini")
FlowSubject = Literal["river_at_border", "treatment_plant", "pipeline_or_pump", "none"]
NUMBER_FIELDS = ("expected_flow_mgd", "flow_delta_mgd", "peak_flow_mgd")


class FlowEvent(BaseModel):
    published_at: datetime
    event_type: Literal["pump_shutdown", "collector_failure", "repair", "diversion", "storm", "other"]
    location_text: str
    starts_at: datetime
    ends_at: datetime | None = None
    flow_subject: FlowSubject = "none"  # what the flow numbers measure; only river_at_border drives the model
    expected_flow_mgd: float | None = None
    flow_delta_mgd: float | None = None
    peak_flow_mgd: float | None = None
    confidence: float = Field(ge=0, le=1)
    quote: str = Field(min_length=10)


class Extraction(BaseModel):
    events: list[FlowEvent]


PROMPT = """You read press releases and stakeholder statements from the U.S. Section of the International Boundary and
Water Commission (USIBWC) about the Tijuana River and South Bay sewage infrastructure.

Extract every event that changes, or is expected to change, the flow of sewage or water in the Tijuana River at the
U.S.-Mexico border: pump station shutdowns, collector or pipe failures, repairs, diversions, and storm flows.

Rules:
- Use only facts stated in the text. Never guess numbers. Leave a number null if the text doesn't state it.
- The flow numbers (expected_flow_mgd, flow_delta_mgd, peak_flow_mgd) mean ONLY the flow in the Tijuana River
  itself as it crosses the border into the U.S. Set flow_subject to say what the stated number measures:
  - "river_at_border": the river's own flow, e.g. "the Tijuana River is flowing at 64 MGD", or a stated change in
    the sewage/water entering the river across the border.
  - "treatment_plant": a treatment plant's capacity or throughput (e.g. the SBIWTP treating up to 35 MGD, a 10 MGD
    expansion). This is NOT river flow.
  - "pipeline_or_pump": flow carried by a pipe, collector, pump station or diversion. This is NOT river flow.
  - "none": no flow number is stated.
  If flow_subject is not "river_at_border", leave all three flow numbers null.
- Every flow number must appear in quote. quote is the one sentence that states it.
- Flows are in million gallons per day (MGD). Convert only if the text gives another unit explicitly.
- Times are Pacific Time; write ISO-8601 with offset. If only a date is given, use 00:00 that day.
- published_at is the release date. If unknown, use starts_at.
- quote must be the exact sentence from the text that the values came from, copied verbatim.
- confidence (0-1) is how clearly the text supports the timing and the flow numbers.
- Return {"events": []} if there are none.

TEXT:
"""


def _numbers(s: str) -> set[float]:
    return {float(m.replace(",", "")) for m in re.findall(r"\d[\d,]*(?:\.\d+)?", s)}


def sanitize(ev: FlowEvent, text: str) -> FlowEvent:
    """Deterministic checks on Gemini's output. Failing events keep their timeline entry but lose their numbers.

    - quote not found verbatim in the source -> confidence capped at 0.5 (below the 0.6 the model uses).
    - flow numbers kept only if they describe the river at the border; each one must also appear in the quote.
    """
    norm = " ".join(text.split())
    if ev.quote.strip() not in norm and ev.quote.strip() not in text:
        ev.confidence = min(ev.confidence, 0.5)
    stated = _numbers(ev.quote)
    vals = {f: getattr(ev, f) for f in NUMBER_FIELDS if getattr(ev, f) is not None}
    drop = list(vals) if ev.flow_subject != "river_at_border" else [f for f, v in vals.items() if abs(v) not in stated]
    if drop:
        log.info("dropping flow numbers %s of %s (subject=%s): %.80s", drop, vals, ev.flow_subject, ev.quote)
        for f in drop:
            setattr(ev, f, None)
    return ev


def event_id(source_url: str, quote: str) -> str:
    return "gem-" + hashlib.sha1(f"{source_url}|{quote}".encode()).hexdigest()[:16]


def extract(text: str, source_url: str) -> list[dict]:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        contents=PROMPT + text[:60_000],
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=Extraction,
                                           temperature=0),
    )
    try:
        parsed = Extraction.model_validate_json(resp.text)
    except ValidationError as e:
        log.warning("gemini output failed validation: %s", e)
        return []
    out = []
    for ev in parsed.events:
        ev = sanitize(ev, text)
        out.append({**json.loads(ev.model_dump_json()), "id": event_id(source_url, ev.quote),
                    "source_url": source_url, "entered_by": "gemini"})
    return out
