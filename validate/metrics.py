"""Skill metrics (spec 5.7)."""
from __future__ import annotations

import numpy as np

from config import ORANGE_PPB

CATS = [(0, "green"), (5, "yellow"), (30, "orange")]


def cat(v):
    c = "green"
    for lo, name in CATS:
        if v >= lo:
            c = name
    return c


def night_scores(fc: np.ndarray, obs: np.ndarray) -> list[dict]:
    """fc, obs: [nights, hours] for one monitor. Returns per-night dicts (NaN obs hours ignored)."""
    out = []
    for f, o in zip(fc, obs):
        ok = np.isfinite(o) & np.isfinite(f)
        if ok.sum() < 6:
            continue
        out.append({"obs_peak": float(o[ok].max()), "fc_peak": float(f[ok].max()),
                    "obs_event": bool(o[ok].max() >= ORANGE_PPB), "fc_event": bool(f[ok].max() >= ORANGE_PPB),
                    "cat_hit": cat(o[ok].max()) == cat(f[ok].max()),
                    "mae_log": float(np.mean(np.abs(np.log1p(np.clip(f[ok], 0, None)) - np.log1p(np.clip(o[ok], 0, None)))))})
    return out


def summarize(scores: list[dict]) -> dict:
    n = len(scores)
    if n == 0:
        return {"n_nights": 0}
    ev = [s for s in scores if s["obs_event"]]
    fc_ev = [s for s in scores if s["fc_event"]]
    return {
        "n_nights": n,
        "n_orange_nights": len(ev),
        "hit_rate": (sum(s["fc_event"] for s in ev) / len(ev)) if ev else None,
        "false_alarm_ratio": (sum(not s["obs_event"] for s in fc_ev) / len(fc_ev)) if fc_ev else None,
        "category_accuracy": sum(s["cat_hit"] for s in scores) / n,
        "mae_log": float(np.mean([s["mae_log"] for s in scores])),
    }
