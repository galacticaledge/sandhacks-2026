"""Shared settings, geography and SDAPCD levels for Smellcast."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

TZ = ZoneInfo("America/Los_Angeles")
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
FORECAST_DIR = DATA_DIR / "forecasts"
DEMO_DIR = DATA_DIR / "demo"
LOG_DIR = ROOT / "logs"

DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{DATA_DIR / 'smellcast.sqlite'}"
if DEMO_MODE:  # seeded snapshot: never touches live sources or the production database
    DATABASE_URL = f"sqlite:///{DEMO_DIR / 'smellcast.sqlite'}"
    FORECAST_DIR = DEMO_DIR / "forecasts"
DEFAULT_FLOW_MGD = float(os.getenv("DEFAULT_FLOW_MGD", "35"))
USER_AGENT = "smellcast-hackathon (South Bay H2S forecast)"

# Grid: spec section 5.3
BBOX = {"lat_min": 32.535, "lat_max": 32.600, "lon_min": -117.140, "lon_max": -117.030}
GRID_M = 50.0
REF_LAT, REF_LON = 32.5675, -117.085  # local tangent-plane origin
RECEPTOR_Z_M = 1.5

# Monitors (verified from the live feed 2026-11-14)
@dataclass(frozen=True)
class Monitor:
    site_id: str
    feed_name: str
    name: str
    lat: float
    lon: float


MONITORS = [
    Monitor("ib_civic", "IB CIVIC CTR", "Imperial Beach Civic Center", 32.576139, -117.115361),
    Monitor("nestor_bes", "NESTOR - BES", "Nestor (Berry Elementary)", 32.567097, -117.090656),
    Monitor("san_ysidro", "SAN YSIDRO", "San Ysidro", 32.552794, -117.047286),
]
MONITOR_BY_FEED = {m.feed_name: m for m in MONITORS}
MONITOR_BY_ID = {m.site_id: m for m in MONITORS}

# SDAPCD Community H2S Guidance levels (spec section 7)
LEVELS = [
    ("green", 0.0, "Green"),
    ("yellow", 5.0, "Yellow"),
    ("orange", 30.0, "Orange"),
    ("review", 200.0, "Multi-agency review"),
]
ORANGE_PPB = 30.0


def level_for(ppb: float | None) -> str | None:
    if ppb is None:
        return None
    lvl = "green"
    for key, lo, _ in LEVELS:
        if ppb >= lo:
            lvl = key
    return lvl


# Verified 2026-11-14
SDAPCD_H2S_URL = "https://www.sdapcd.org/content/sdapcd/about/tj-river-valley/tjrv-air-quality-monitoring.html"
SDAPCD_TJRV_URL = "https://www.sdapcd.org/content/sdapcd/about/tj-river-valley.html"
SDAPCD_ALERTS_URL = "https://public.govdelivery.com/accounts/CASDCAPCD/subscriber/new"
SDAPCD_GUIDANCE_EN = "https://www.sdapcd.org/content/dam/sdapcd/documents/tjrv/Community%20H2S%20Guidance_11.13.24_ENGLISH.pdf"
SDAPCD_GUIDANCE_ES = "https://www.sdapcd.org/content/dam/sdapcd/documents/tjrv/Community%20H2S%20Guidance_11.13.24_SPANISH.pdf"
SDAPCD_POWERBI_URL = ("https://app.powerbigov.us/view?r=eyJrIjoiNzU5YzE4NjAtZTZhMS00ZDg3LTkwMzktYzRiMjkzNDY5ZmU2Iiwid"
                      "CI6IjQ1NjNhZjEzLWMwMjktNDFiMy1iNzRjLTk2NWU4ZWVjOGY5NiJ9")
RESILIENT_SHIELD_URL = "https://resilientshield.ucsd.edu/"

for _d in (RAW_DIR, FORECAST_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

NWS_GRID = ("SGX", 58, 7)  # api.weather.gov/points/32.565,-117.09
PAST_WX_STATION = "NRS"  # KNRS Imperial Beach NOLF, 32.5631,-117.1100 (in the river valley)
