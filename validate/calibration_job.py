"""Fit the calibration (spec 5.4) on the monitor history with observed weather.

Two fits, both on data before TUNE_END only, so every night from TUNE_END on is a clean held-out test:
  1. physics: log k, alpha, beta, source shares, backgrounds, storm-water dilution (least squares, hourly)
  2. monitor correction (model/blend.py): night-peak regression on the physics forecast + recent readings

python -m validate.calibration_job            # fit on nights before 2026-01-01, write data/calibration.json
python -m validate.calibration_job --all      # fit on everything (no held-out period left: not for scoring)
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from db import store
from model.inputs import CALIBRATION_PATH
from validate import hindcast

log = logging.getLogger("calibrate")
UTC = timezone.utc


def run_calibration(fit_all: bool = False) -> dict | None:
    a, b, n = store.reading_range()
    if not a or n < 24 * 30:
        log.warning("not enough data to calibrate")
        return None
    hc, cal = hindcast.calibrate_all(None if fit_all else hindcast.TUNE_END)
    cal["fitted_at"] = datetime.now(UTC).isoformat()
    cal["window"] = [a.isoformat(), (min(b, datetime(*hindcast.TUNE_END.timetuple()[:3], tzinfo=UTC)) if not fit_all else b).isoformat()]
    CALIBRATION_PATH.write_text(json.dumps(cal, indent=1))
    log.info("calibration: %s", {k: v for k, v in cal.items() if k != "blend"})
    return cal


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_calibration("--all" in sys.argv), indent=1))
