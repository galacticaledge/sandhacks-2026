"""Baselines we must beat (spec 5.7): persistence and climatology."""
from __future__ import annotations

from datetime import datetime, timedelta

import warnings

import numpy as np

from model.inputs import hours, observations


def persistence(night_times: list[datetime]) -> np.ndarray:
    """Tonight looks like last night: same hours, 24 h earlier. [H, M]"""
    return observations([t - timedelta(hours=24) for t in night_times])


def climatology(night_times: list[datetime], issued: datetime, days: int = 30) -> np.ndarray:
    """Mean observed value for each hour of day over the `days` before issue. [H, M]"""
    past = hours(issued - timedelta(days=days), days * 24)
    obs = observations(past)
    hod = np.array([t.astimezone(night_times[0].tzinfo).hour for t in past])
    out = np.full((len(night_times), obs.shape[1]), np.nan)
    for i, t in enumerate(night_times):
        sel = obs[hod == t.hour]
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            out[i] = np.nanmean(sel, axis=0) if np.isfinite(sel).any() else np.nan
    return out
