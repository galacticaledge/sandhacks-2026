"""Evening alert rules (spec 7). Pure functions over a run's receptor series."""
from __future__ import annotations

from datetime import datetime

from config import ORANGE_PPB, level_for
from model.ensemble import confidence_label

NIGHT_START_H, NIGHT_END_H = 18, 9  # 6 PM -> 9 AM local


def in_night(t: datetime) -> bool:
    return t.hour >= NIGHT_START_H or t.hour < NIGHT_END_H


def night_window(valid_times: list[datetime]) -> list[int]:
    """Indices of the first contiguous 6 PM-9 AM window in the run."""
    idx, started = [], False
    for i, t in enumerate(valid_times):
        if in_night(t):
            idx.append(i); started = True
        elif started:
            break
    return idx


def evaluate(valid_times: list[datetime], p10: list[float], p50: list[float], p90: list[float]) -> dict:
    w = night_window(valid_times)
    if not w:
        return {"kind": "none", "window": None}
    i50 = max(w, key=lambda i: p50[i])
    i90 = max(w, key=lambda i: p90[i])
    peak50, peak90 = p50[i50], p90[i90]
    if peak50 >= ORANGE_PPB:
        kind = "likely"
    elif peak90 >= ORANGE_PPB:
        kind = "possible"
    else:
        kind = "none"
    above = [i for i in w if (p50[i] if kind == "likely" else p90[i]) >= ORANGE_PPB]
    # From the two peaks we display, even when they fall in different hours: a wide gap must not read as "high".
    conf = confidence_label(peak50, peak90)
    if kind == "possible":
        conf = "low"
    return {
        "kind": kind,
        "peak_p50": round(peak50, 1), "peak_p90": round(peak90, 1), "peak_p10": round(p10[i50], 1),
        "peak_time": valid_times[i50].isoformat(), "level": level_for(peak50), "level_p90": level_for(peak90),
        "confidence": conf,
        "window": [valid_times[w[0]].isoformat(), valid_times[w[-1]].isoformat()],
        "orange_window": [valid_times[above[0]].isoformat(), valid_times[above[-1]].isoformat()] if above else None,
    }
