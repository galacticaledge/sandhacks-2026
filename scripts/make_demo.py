"""Freeze the current state into data/demo/ for DEMO_MODE=1 (spec 2: seeded snapshot if a live source fails).

Keeps the latest live run and the worst held-out nights when the gas reached every monitor
(validate.replay.widespread_nights), each replayed with a map using the current calibration; the worst one is
featured, and the Replay list shows only those nights. The whole database is copied. --trim keeps only what those
runs show (readings, weather and complaints from a week before each night to two days after, river flow for the 60
days before, the forecast rows of the kept runs) for a smaller file.

    python -m scripts.make_demo                 # the 5 worst nights in the Replay list, full database
    python -m scripts.make_demo --nights 3      # fewer nights in the list
    python -m scripts.make_demo --trim          # also trim the database to the data around those nights
    python -m scripts.make_demo --all-replays   # every replay run that has a map
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, datetime, timedelta, timezone

from config import DEMO_DIR, FORECAST_DIR
from db import store

UTC = timezone.utc
TABLES = ["h2s_readings", "receptor_forecasts", "weather_hourly", "source_fetches", "flow_daily", "flow_events",
          "model_runs", "complaints", "spills", "skill_scores", "web_reports"]
TIME_COL = {"h2s_readings": "observed_at", "weather_hourly": "observed_at", "complaints": "received_at",
            "source_fetches": "fetched_at", "web_reports": "published_at"}
RUN_TABLES = ("receptor_forecasts", "model_runs")
BEFORE, AFTER, FLOW_DAYS = timedelta(days=8), timedelta(days=2), 60


def windows(run_ids: list[str]) -> list[tuple[datetime, datetime]]:
    """Time spans the kept runs show: a week of context before each issue time, two days after."""
    out = []
    for rid in run_ids:
        meta = FORECAST_DIR / rid / "meta.json"
        if meta.exists():
            t = datetime.fromisoformat(json.loads(meta.read_text())["issued_at"]).astimezone(UTC)
            out.append((t - (BEFORE if rid.endswith("-replay") else timedelta(days=3)), t + AFTER))
    return out


def keep_row(table: str, r: dict, spans: list[tuple[datetime, datetime]], run_ids: set[str]) -> bool:
    if table in RUN_TABLES:
        return r.get("run_id") in run_ids
    if table == "flow_daily":
        d = r["date"] if isinstance(r["date"], date) else date.fromisoformat(str(r["date"])[:10])
        return any(a.date() - timedelta(days=FLOW_DAYS) <= d <= b.date() for a, b in spans)
    col = TIME_COL.get(table)
    if not col:
        return True                      # small tables (flow events, spills, scores): keep whole
    t = r.get(col)
    if t is None:
        return table == "web_reports"
    t = store.dt(t).astimezone(UTC)
    return any(a <= t <= b for a, b in spans)


def main(n_nights: int = 5, all_replays: bool = False, trim: bool = False):
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    (DEMO_DIR / "forecasts").mkdir(exist_ok=True)
    keep = [r["run_id"] for r in store.runs("live", limit=1)]
    if all_replays:
        keep += [r["run_id"] for r in store.runs("replay", limit=500)
                 if (FORECAST_DIR / r["run_id"] / "p50.npy").exists()]
    else:
        keep += seed_bad_nights(n_nights)
    spans, ids = windows(keep), set(keep)

    db = DEMO_DIR / "smellcast.sqlite"
    if db.exists():
        db.unlink()
    from sqlalchemy import create_engine, text
    eng = create_engine(f"sqlite:///{db}")
    tiger = (store.HERE / "tiger_schema.sql").read_text() + (store.HERE / "app_schema.sql").read_text()
    counts = {}
    with eng.begin() as c:
        for s in store._statements(tiger):
            if s.upper().startswith("CREATE TABLE"):
                c.execute(text(s.replace("TIMESTAMPTZ", "TEXT")))
        for t in TABLES:
            rows = [r for r in store.query(f"SELECT * FROM {t}") if not trim or keep_row(t, r, spans, ids)]
            counts[t] = len(rows)
            if not rows:
                continue
            cols = list(rows[0].keys())
            for r in rows:
                for k, v in r.items():
                    if isinstance(v, datetime):
                        r[k] = v.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
            c.execute(text(f"INSERT OR REPLACE INTO {t} ({','.join(cols)}) VALUES ({','.join(':' + x for x in cols)})"), rows)
    with eng.connect() as c:
        c.execution_options(isolation_level="AUTOCOMMIT").execute(text("VACUUM"))

    for old in (DEMO_DIR / "forecasts").glob("*"):   # the snapshot shows exactly the runs chosen here
        if old.name not in ids:
            shutil.rmtree(old)
    n = 0
    for rid in keep:
        src = FORECAST_DIR / rid
        if src.exists() and (rid.endswith("-replay") is False or (src / "p50.npy").exists()):
            dst = DEMO_DIR / "forecasts" / rid
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst); n += 1
    cal, skill = FORECAST_DIR.parent / "calibration.json", FORECAST_DIR.parent / "skill.json"
    if cal.exists():
        shutil.copy(cal, DEMO_DIR / cal.name)
    # scores are only valid for the calibration they were computed with
    if skill.exists() and (not cal.exists() or skill.stat().st_mtime > cal.stat().st_mtime):
        shutil.copy(skill, DEMO_DIR / skill.name)
    else:
        print("kept the demo's skill.json: data/skill.json predates the current calibration (run python -m validate.replay)")
    (DEMO_DIR / "README.md").write_text(f"Demo snapshot frozen {datetime.now(UTC).isoformat()} with {n} runs"
                                        f"{' (database trimmed to what those runs show)' if trim else ''}.\n")
    print("rows:", ", ".join(f"{t} {k}" for t, k in counts.items()))
    print("demo snapshot:", db, n, "runs")


def seed_bad_nights(n: int) -> list[str]:
    """Replay (with a map) the n worst widespread held-out nights and feature the worst one. Returns run ids."""
    from api.routes.validation import _default_receptor
    from validate.replay import replay_night, widespread_nights
    nights = widespread_nights(n)
    metas = [replay_night(d, grid=True) for d in nights]
    if metas:
        feat = {"night": nights[0].isoformat(), "receptor_id": _default_receptor(metas[0]),
                "nights": [d.isoformat() for d in nights]}
        (DEMO_DIR / "featured_night.json").write_text(json.dumps(feat) + "\n")
        print("featured", feat)
    print("bad nights:", ", ".join(d.isoformat() for d in nights))
    return [m["run_id"] for m in metas]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--nights", type=int, default=5)
    ap.add_argument("--all-replays", action="store_true")
    ap.add_argument("--trim", action="store_true", help="keep only the data around the kept nights (smaller file)")
    a = ap.parse_args()
    main(a.nights, a.all_replays, a.trim)
