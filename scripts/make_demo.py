"""Freeze the current state into data/demo/ for DEMO_MODE=1 (spec 2: seeded snapshot if a live source fails).

Copies the live DB rows (via SQLite), the latest live run and all replay runs with grids.
    python -m scripts.make_demo
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timezone

from config import DEMO_DIR, FORECAST_DIR
from db import store

TABLES = ["h2s_readings", "receptor_forecasts", "weather_hourly", "source_fetches", "flow_daily", "flow_events",
          "model_runs", "complaints", "spills", "skill_scores"]


def main():
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    (DEMO_DIR / "forecasts").mkdir(exist_ok=True)
    db = DEMO_DIR / "smellcast.sqlite"
    if db.exists():
        db.unlink()
    from sqlalchemy import create_engine, text
    eng = create_engine(f"sqlite:///{db}")
    import re
    tiger = (store.HERE / "tiger_schema.sql").read_text() + (store.HERE / "app_schema.sql").read_text()
    with eng.begin() as c:
        for s in store._statements(tiger):
            if s.upper().startswith("CREATE TABLE"):
                c.execute(text(s.replace("TIMESTAMPTZ", "TEXT")))
        for t in TABLES:
            rows = store.query(f"SELECT * FROM {t}")
            if not rows:
                continue
            cols = list(rows[0].keys())
            for r in rows:
                for k, v in r.items():
                    if isinstance(v, datetime):
                        r[k] = v.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
            c.execute(text(f"INSERT OR REPLACE INTO {t} ({','.join(cols)}) VALUES ({','.join(':' + x for x in cols)})"), rows)
    keep = [r["run_id"] for r in store.runs("live", limit=1)] + [r["run_id"] for r in store.runs("replay", limit=500)]
    n = 0
    for rid in keep:
        src = FORECAST_DIR / rid
        if src.exists() and (rid.endswith("-replay") is False or (src / "p50.npy").exists()):
            dst = DEMO_DIR / "forecasts" / rid
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst); n += 1
    for f in ("skill.json", "calibration.json"):
        if (FORECAST_DIR.parent / f).exists():
            shutil.copy(FORECAST_DIR.parent / f, DEMO_DIR / f)
    (DEMO_DIR / "README.md").write_text(f"Demo snapshot frozen {datetime.now(timezone.utc).isoformat()} with {n} runs.\n")
    print("demo snapshot:", db, n, "runs")


if __name__ == "__main__":
    main()
