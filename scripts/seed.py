"""Seed a database (local TimescaleDB, Tiger Cloud or SQLite) with everything the app needs to look complete:
monitor history, weather, river flow, complaints, announcements, a calibration, and map replays of the worst nights.

Works in live mode against $DATABASE_URL; every step is idempotent (upserts, cached downloads), so rerunning is safe.
Steps that need a key are skipped without it. For the frozen demo snapshot use scripts.make_demo instead.

    python -m scripts.seed                       # everything
    python -m scripts.seed --nights 3            # fewer bad nights
    python -m scripts.seed --skip flow reports   # leave steps out
    python -m scripts.seed --only replays        # just (re)make the bad-night replays
    python -m scripts.seed --score               # also replay every night and score them (hours)
    python -m scripts.seed --once                # skip if these steps already finished (data/.seeded.json)
    python -m scripts.seed --small               # demo: every step, Replay list capped at the 5 worst nights

In Docker/Podman set SEED=1 in .env: the app container runs `scripts.seed --once $SEED_ARGS` in the background on
start (api/main.py), logging to logs/seed.log. SEED=small does the same with --small; SEED=always reseeds every start.
Seeding never shrinks the data: it only decides which bad nights get maps and appear in the Replay list.

Steps, in order:
  history        hourly H2S since Dec 2023 (UCSD Resilient Shield yearly files)
  weather        observed KNRS weather for the same period (Iowa Environmental Mesonet; rate-limited, retried)
  flow           USIBWC river flow history. NOTE: the collector accepts the USIBWC Water Data Portal disclaimer
  complaints     SDAPCD odor complaints and sewage spills
  announcements  USIBWC press releases; Gemini turns them into flow events (needs GEMINI_API_KEY)
  calibrate      fit the model on nights before 2026 (the held-out split the Accuracy page uses)
  replays        replay the worst nights when gas reached every monitor, with maps; feature the worst one
  reports        news reports for those nights via Bright Data + Gemini (needs BRIGHTDATA_API_TOKEN,
                 BRIGHTDATA_UNLOCKER_ZONE and GEMINI_API_KEY; spends Bright Data credit)
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from config import DATA_DIR, DEMO_DIR, DEMO_MODE, FORECAST_DIR

log = logging.getLogger("seed")
UTC = timezone.utc
STEPS = ["history", "weather", "flow", "complaints", "announcements", "calibrate", "replays", "reports"]
SMALL_NIGHTS = 5   # demo: at most this many bad nights (orange at every monitor), worst first
HISTORY_START = datetime(2023, 12, 20, tzinfo=UTC)
MARKER = DATA_DIR / ".seeded.json"   # steps that finished without errors, for --once
LOCK = DATA_DIR / ".seed.lock"


def done_steps() -> set[str]:
    try:
        return set(json.loads(MARKER.read_text()).get("steps", []))
    except (OSError, ValueError):
        return set()


def mark_done(steps: list[str], nights: int):
    MARKER.write_text(json.dumps({"seeded_at": datetime.now(UTC).isoformat(), "nights": nights,
                                  "steps": sorted(done_steps() | set(steps))}, indent=1) + "\n")


def step_history() -> str:
    from collectors.h2s_history import download, load
    return f"{load(download())} readings upserted"


def step_weather() -> str:
    from collectors.weather_archive import backfill_weather
    n, a, end = 0, HISTORY_START, datetime.now(UTC) + timedelta(days=1)
    while a < end:   # half-year chunks: the archive rate-limits large requests
        b = min(datetime(a.year + (a.month > 6), 1 if a.month > 6 else 7, 1, tzinfo=UTC), end)
        for attempt in range(6):
            try:
                n += backfill_weather(a, b)
                break
            except Exception as e:  # 429 Too Many Requests: wait and retry
                log.warning("weather %s: %s; retry %d in 90 s", a.date(), str(e)[:80], attempt + 1)
                time.sleep(90)
        a = b
    return f"{n} hours added"


def step_flow() -> str:
    from collectors.usibwc_flow import fetch_flow
    log.info("flow: the USIBWC collector accepts the Water Data Portal disclaimer on your behalf")
    return f"{fetch_flow()} days"


def step_complaints() -> str:
    from collectors.complaints import poll_complaints
    from collectors.spills import poll_spills
    return f"{poll_complaints()} complaints, {poll_spills()} spills"


def step_announcements() -> str:
    from collectors.announcements import fetch_announcements
    if not os.getenv("GEMINI_API_KEY"):
        return "skipped: GEMINI_API_KEY not set"
    return f"{fetch_announcements()} flow events"


def step_calibrate() -> str:
    from validate.calibration_job import run_calibration
    cal = run_calibration()
    return f"fitted on nights before {cal['fit_before']}" if cal else "skipped: not enough history"


def step_replays(n_nights: int) -> str:
    from api.routes.validation import _default_receptor
    from validate.replay import replay_night, widespread_nights
    nights = widespread_nights(n_nights)
    if not nights:
        return "no night reached orange at every monitor (load history first)"
    metas = []
    for d in nights:
        log.info("replaying %s with a map", d)
        metas.append(replay_night(d, grid=True))
    feat = {"night": nights[0].isoformat(), "receptor_id": _default_receptor(metas[0]),
            "nights": [d.isoformat() for d in nights]}   # the Replay list shows only these (REPLAY_LIST=all: every night)
    (DATA_DIR / "featured_night.json").write_text(json.dumps(feat) + "\n")
    return f"{', '.join(feat['nights'])}; featured {feat['night']} at {feat['receptor_id']}"


def step_demo_replays() -> str:
    """Use the bad-night maps shipped in data/demo/ (committed) instead of computing them: copies the replay runs,
    the featured-night list and, if none exists yet, the calibration they were made with."""
    import shutil
    FORECAST_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for src in sorted((DEMO_DIR / "forecasts").glob("*-replay")):
        if not (FORECAST_DIR / src.name).exists():
            shutil.copytree(src, FORECAST_DIR / src.name); n += 1
    shutil.copy(DEMO_DIR / "featured_night.json", DATA_DIR / "featured_night.json")
    if not (DATA_DIR / "calibration.json").exists():
        shutil.copy(DEMO_DIR / "calibration.json", DATA_DIR / "calibration.json")
    return f"copied {n} replay maps from data/demo; Replay list = {json.loads((DATA_DIR / 'featured_night.json').read_text()).get('nights')}"


def step_reports(n_nights: int) -> str:
    need = ("BRIGHTDATA_API_TOKEN", "BRIGHTDATA_UNLOCKER_ZONE", "GEMINI_API_KEY")
    missing = [k for k in need if not os.getenv(k)]
    if missing:
        return "skipped: " + ", ".join(missing) + " not set"
    from collectors.web_reports import fetch_reports
    from validate.replay import widespread_nights
    out = []
    for d in widespread_nights(n_nights):
        r = fetch_reports(d, d + timedelta(days=2))   # coverage usually lands the day of or the day after
        out.append(f"{d}: {r}")
    return "; ".join(out)


def score() -> str:
    from validate.replay import run_all_replays
    r = run_all_replays(grid_nights=0)
    return f"{r.get('n_scored', 0)} nights scored"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nights", type=int, default=None, help="bad nights to replay with maps (default 5; 2 with --small)")
    ap.add_argument("--small", action="store_true", help=f"demo: cap the Replay list at {SMALL_NIGHTS} nights")
    ap.add_argument("--skip", nargs="*", default=[], choices=STEPS, metavar="STEP")
    ap.add_argument("--only", nargs="*", default=None, choices=STEPS, metavar="STEP")
    ap.add_argument("--score", action="store_true", help="also replay and score every night (takes hours)")
    ap.add_argument("--from-demo", action="store_true",
                    help="fast (~2 min): readings + the 5 bad-night maps shipped in data/demo, no recomputing")
    ap.add_argument("--once", action="store_true", help="do nothing if these steps already finished (data/.seeded.json)")
    a = ap.parse_args(argv)
    if DEMO_MODE:
        print("DEMO_MODE=1 points at the frozen snapshot; unset it to seed a live database (or use scripts.make_demo).")
        return 1
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    a.nights = min(a.nights or SMALL_NIGHTS, SMALL_NIGHTS) if a.small else (a.nights or 5)
    run = [s for s in (a.only or (["history", "complaints", "demo_replays"] if a.from_demo else STEPS)) if s not in a.skip]
    if a.once and set(run) <= done_steps():
        print(f"already seeded ({', '.join(run)}); delete {MARKER} or use SEED=always to seed again")
        return 0
    lock = open(LOCK, "w")
    try:   # one seed at a time (a container restart can start a second one)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another seed is already running")
        return 0
    from db import store
    store.init_db()
    fns = {"history": step_history, "weather": step_weather, "flow": step_flow, "complaints": step_complaints,
           "announcements": step_announcements, "calibrate": step_calibrate,
           "replays": lambda: step_replays(a.nights), "demo_replays": step_demo_replays, "reports": lambda: step_reports(a.nights)}
    results, failed = [], 0
    for s in run:
        t = time.time()
        try:
            msg = fns[s]()
        except Exception as e:   # keep going: later steps can still use what earlier ones loaded
            log.exception("step %s failed", s)
            msg, failed = f"FAILED: {e}", failed + 1
        results.append((s, msg, time.time() - t))
        log.info("%s: %s", s, msg)
    if a.score:
        results.append(("score", score(), 0.0))
    ok = [s for s, msg, _ in results if not msg.startswith("FAILED")]
    mark_done(ok, a.nights)
    print("\nseed summary")
    for s, msg, dt in results:
        print(f"  {s:13s} {msg}" + (f"  ({dt:.0f} s)" if dt >= 1 else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
