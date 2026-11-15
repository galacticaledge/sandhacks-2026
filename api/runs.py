"""Read forecast runs from disk (grids) and the database."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from functools import lru_cache

import numpy as np

from config import FORECAST_DIR, TZ
from db import store
from model.geo import grid_from_meta

RUN_RE = re.compile(r"^[0-9]{8}T[0-9]{4}Z(-[a-z]+)?$")


def valid_run_id(run_id: str) -> bool:
    return bool(RUN_RE.match(run_id)) and (FORECAST_DIR / run_id / "meta.json").exists()


@lru_cache(maxsize=32)
def load_meta(run_id: str) -> dict:
    return json.loads((FORECAST_DIR / run_id / "meta.json").read_text())


def latest_run_id(scenario: str = "live") -> str | None:
    for r in store.runs(scenario, limit=10):
        if valid_run_id(r["run_id"]):
            return r["run_id"]
    # fall back to disk (e.g. demo snapshot)
    ids = sorted(p.name for p in FORECAST_DIR.glob("*") if RUN_RE.match(p.name) and (p / "meta.json").exists()
                 and (scenario == "live") == ("-" not in p.name))
    return ids[-1] if ids else None


def evening_run_id(now: datetime | None = None) -> tuple[str | None, str]:
    """The 5 PM run that feeds tonight's alerts; falls back to the latest run before 5 PM."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    target = now.replace(hour=17, minute=0, second=0, microsecond=0)
    if now.hour < 12:  # early morning: tonight's run was yesterday's 5 PM
        target -= timedelta(days=1)
    for r in store.runs("live", limit=48):
        if r["issued_at"].astimezone(TZ) == target and valid_run_id(r["run_id"]):
            return r["run_id"], "5 PM run"
    return latest_run_id(), "latest run (5 PM run not issued yet)"


@lru_cache(maxsize=4)
def _grid_arrays(run_id: str):
    d = FORECAST_DIR / run_id
    return {p: np.load(d / f"{p}.npy", mmap_mode="r") for p in ("p10", "p50", "p90")}


@lru_cache(maxsize=8)
def run_grid(run_id: str):
    """The grid this run was computed on (older runs used a smaller box at 50 m)."""
    return grid_from_meta(load_meta(run_id)["grid"])


def point_series(run_id: str, lat: float, lon: float) -> dict | None:
    g = run_grid(run_id)
    ij = g.index_of(lat, lon)
    if ij is None:
        return None
    arr = _grid_arrays(run_id)
    i, j = ij
    return {p: np.round(arr[p][:, i, j].astype(float), 2).tolist() for p in arr}
