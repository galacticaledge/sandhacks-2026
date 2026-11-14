"""APScheduler jobs (spec 4): idempotent, logged, unattended."""
from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from config import TZ

log = logging.getLogger("scheduler")


def _job(name, fn, *a, **kw):
    def run():
        t = datetime.now(TZ)
        try:
            r = fn(*a, **kw)
            log.info("job %s ok (%s) in %.1fs", name, r if not isinstance(r, dict) else "dict", (datetime.now(TZ) - t).total_seconds())
        except Exception:
            log.exception("job %s failed", name)
    run.__name__ = run.__qualname__ = name
    return run


def forecast():
    from collectors.nws import fetch_nws_forecast
    from collectors.weather_archive import refresh_recent
    from model.run import run_forecast
    for f in (refresh_recent, fetch_nws_forecast):
        try:
            f()
        except Exception:
            log.exception("pre-forecast fetch failed; running with cached data")
    return run_forecast()["run_id"]


def alerts(update: bool):
    """5:15 PM: decide tonight's alerts from the 5 PM run. 11:15 PM: upgrade to likely orange if needed."""
    from alerts.send import send_for_hour
    return send_for_hour(23 if update else 17, update=update)


def nightly_validation():
    from validate.calibration_job import run_calibration
    from validate.replay import run_all_replays
    run_calibration()
    run_all_replays(grid_nights=3)


def start() -> BackgroundScheduler:
    from collectors.announcements import fetch_announcements
    from collectors.complaints import poll_complaints
    from collectors.h2s_feed import poll_h2s
    from collectors.nws import fetch_nws_forecast
    from collectors.spills import poll_spills
    from collectors.usibwc_flow import fetch_flow
    from collectors.weather_archive import refresh_recent

    s = BackgroundScheduler(timezone=TZ, job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 600})
    now = datetime.now(TZ)
    s.add_job(_job("poll_h2s", poll_h2s), "interval", minutes=15, next_run_time=now)
    s.add_job(_job("poll_complaints", poll_complaints), "interval", minutes=30, next_run_time=now)
    s.add_job(_job("poll_spills", poll_spills), "interval", minutes=30, next_run_time=now)
    s.add_job(_job("fetch_nws_forecast", fetch_nws_forecast), "interval", hours=1, next_run_time=now)
    s.add_job(_job("refresh_recent_weather", refresh_recent), "interval", hours=1, next_run_time=now)
    s.add_job(_job("fetch_flow", fetch_flow), "cron", hour=6, minute=10)
    s.add_job(_job("fetch_announcements", fetch_announcements), "interval", hours=6, next_run_time=now)
    # hourly forecast at :05 (after the :00-:59 hourly averages land); the 17:05 run is the guaranteed 5 PM run
    s.add_job(_job("run_forecast", forecast), "cron", minute=5)
    s.add_job(_job("evening_alerts", alerts, False), "cron", hour=17, minute=15)
    s.add_job(_job("update_alerts", alerts, True), "cron", hour=23, minute=15)
    s.add_job(_job("nightly_validation", nightly_validation), "cron", hour=3, minute=30)
    s.start()
    log.info("scheduler started with %d jobs", len(s.get_jobs()))
    return s
