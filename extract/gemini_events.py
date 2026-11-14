"""Gemini turns commission announcements into structured flow events (spec 6). It never produces a concentration."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger("gemini")


class FlowEvent(BaseModel):
    published_at: datetime
    event_type: Literal["pump_shutdown", "collector_failure", "repair", "diversion", "storm", "other"]
    location_text: str
    starts_at: datetime
    ends_at: datetime | None = None
    expected_flow_mgd: float | None = None
    flow_delta_mgd: float | None = None
    peak_flow_mgd: float | None = None
    # What the MGD numbers measure. Only river flow at the border may change the model's flow.
    flow_refers_to: Literal["river_at_border", "plant_or_pipe", "other"] = "other"
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
- flow_refers_to says what the MGD numbers measure: "river_at_border" only when the sentence gives the total flow of
  the Tijuana River itself crossing the border; "plant_or_pipe" for treatment-plant capacity or throughput, pump
  station or collector flows, diversions, and volumes spilled, bypassed or kept out of the river; "other" otherwise.
- expected_flow_mgd is the total river flow at the border; flow_delta_mgd is a change in that total. If the numbers
  are about a plant, pump or pipe, still record the event but leave expected_flow_mgd and flow_delta_mgd null.
- Flows are in million gallons per day (MGD). Convert only if the text gives another unit explicitly.
- Times are Pacific Time; write ISO-8601 with offset. If only a date is given, use 00:00 that day.
- published_at is the release date. If unknown, use starts_at.
- quote must be the exact sentence from the text that the values came from, copied verbatim.
- confidence (0-1) is how clearly the text supports the timing and the flow numbers.
- Return {"events": []} if there are none.

TEXT:
"""


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
        if ev.quote.strip() not in " ".join(text.split()) and ev.quote.strip() not in text:
            ev.confidence = min(ev.confidence, 0.5)  # quote not found verbatim -> don't let it drive the model
        if ev.flow_refers_to != "river_at_border":  # plant capacity or pipe flow must never stand in for river flow
            ev.expected_flow_mgd = ev.flow_delta_mgd = None
        out.append({**json.loads(ev.model_dump_json()), "id": event_id(source_url, ev.quote),
                    "source_url": source_url, "entered_by": "gemini"})
    return out
