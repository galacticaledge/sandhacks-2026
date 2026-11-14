"""Single-database access layer. Tiger Data (TimescaleDB) in production; SQLite fallback locally.

Timestamps are stored in UTC. On SQLite they are ISO-8601 strings (lexicographically sortable).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config import DATABASE_URL

log = logging.getLogger("db")
HERE = Path(__file__).resolve().parent
UTC = timezone.utc


@lru_cache(maxsize=1)
def engine() -> Engine:
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    kw = {"pool_pre_ping": True} if not url.startswith("sqlite") else {"connect_args": {"timeout": 30}}
    return create_engine(url, future=True, **kw)


def is_sqlite() -> bool:
    return engine().dialect.name == "sqlite"


def ts(dt: datetime | None):
    if dt is None:
        return None
    if dt.tzinfo is None:
        raise ValueError("naive datetime")
    dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00") if is_sqlite() else dt


def dt(v) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, str):
        v = datetime.fromisoformat(v.replace("Z", "+00:00"))
    if isinstance(v, datetime) and v.tzinfo is None:
        v = v.replace(tzinfo=UTC)
    return v


def _statements(sql: str) -> list[str]:
    sql = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in sql.split(";") if s.strip()]


def init_db():
    tiger = (HERE / "tiger_schema.sql").read_text()
    app = (HERE / "app_schema.sql").read_text()
    if is_sqlite():
        with engine().begin() as c:
            for s in _statements(tiger) + _statements(app):
                if s.upper().startswith("CREATE TABLE"):
                    c.execute(text(s.replace("TIMESTAMPTZ", "TEXT")))
        return
    with engine().connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        for s in _statements(tiger) + _statements(app):
            try:
                c.execute(text(s))
            except Exception as e:  # e.g. plain Postgres without timescaledb: keep the tables
                log.warning("schema statement skipped: %s ... (%s)", s[:60], str(e).splitlines()[0])


def execute(sql: str, params: dict | list[dict] | None = None):
    with engine().begin() as c:
        return c.execute(text(sql), params or {})


def query(sql: str, params: dict | None = None) -> list[dict[str, Any]]:
    with engine().connect() as c:
        return [dict(r._mapping) for r in c.execute(text(sql), params or {})]


# ---------- readings ----------
def upsert_readings(rows: Iterable[dict]):
    rows = [{**r, "observed_at": ts(r["observed_at"])} for r in rows]
    if not rows:
        return 0
    execute("""INSERT INTO h2s_readings (observed_at, site_id, ppb, level, source)
               VALUES (:observed_at, :site_id, :ppb, :level, :source)
               ON CONFLICT (site_id, observed_at) DO UPDATE SET ppb = excluded.ppb,
               level = excluded.level, source = excluded.source""", rows)
    return len(rows)


def readings(start: datetime, end: datetime) -> list[dict]:
    rows = query("""SELECT observed_at, site_id, ppb, level, source FROM h2s_readings
                    WHERE observed_at >= :a AND observed_at < :b ORDER BY observed_at""",
                 {"a": ts(start), "b": ts(end)})
    for r in rows:
        r["observed_at"] = dt(r["observed_at"])
    return rows


def latest_readings() -> list[dict]:
    rows = query("""SELECT r.observed_at, r.site_id, r.ppb, r.level FROM h2s_readings r
                    JOIN (SELECT site_id, max(observed_at) m FROM h2s_readings WHERE ppb IS NOT NULL
                          GROUP BY site_id) x ON x.site_id = r.site_id AND x.m = r.observed_at""")
    for r in rows:
        r["observed_at"] = dt(r["observed_at"])
    return rows


def reading_range() -> tuple[datetime | None, datetime | None, int]:
    r = query("SELECT min(observed_at) a, max(observed_at) b, count(*) n FROM h2s_readings")[0]
    return dt(r["a"]), dt(r["b"]), int(r["n"] or 0)


# ---------- weather ----------
def upsert_weather(rows: Iterable[dict]):
    rows = [{**r, "observed_at": ts(r["observed_at"]), "issued_at": ts(r.get("issued_at"))} for r in rows]
    if not rows:
        return 0
    execute("""INSERT INTO weather_hourly (observed_at, station, kind, issued_at, wind_ms, wind_dir_deg, temp_c, cloud_frac)
               VALUES (:observed_at, :station, :kind, :issued_at, :wind_ms, :wind_dir_deg, :temp_c, :cloud_frac)
               ON CONFLICT (station, kind, observed_at) DO UPDATE SET issued_at = excluded.issued_at,
               wind_ms = excluded.wind_ms, wind_dir_deg = excluded.wind_dir_deg, temp_c = excluded.temp_c,
               cloud_frac = excluded.cloud_frac""", rows)
    return len(rows)


def weather(kind: str, start: datetime, end: datetime, station: str | None = None) -> list[dict]:
    sql = """SELECT * FROM weather_hourly WHERE kind = :k AND observed_at >= :a AND observed_at < :b"""
    p = {"k": kind, "a": ts(start), "b": ts(end)}
    if station:
        sql += " AND station = :s"; p["s"] = station
    rows = query(sql + " ORDER BY observed_at", p)
    for r in rows:
        r["observed_at"] = dt(r["observed_at"]); r["issued_at"] = dt(r["issued_at"])
    return rows


# ---------- forecasts / runs ----------
def upsert_receptor_forecasts(rows: list[dict]):
    rows = [{**r, "issued_at": ts(r["issued_at"]), "valid_at": ts(r["valid_at"])} for r in rows]
    if rows:
        execute("""INSERT INTO receptor_forecasts (scenario, issued_at, valid_at, receptor_id, p10, p50, p90, run_id)
                   VALUES (:scenario, :issued_at, :valid_at, :receptor_id, :p10, :p50, :p90, :run_id)
                   ON CONFLICT (scenario, receptor_id, issued_at, valid_at) DO UPDATE SET p10 = excluded.p10,
                   p50 = excluded.p50, p90 = excluded.p90, run_id = excluded.run_id""", rows)


def receptor_forecasts(run_id: str) -> list[dict]:
    rows = query("SELECT * FROM receptor_forecasts WHERE run_id = :r ORDER BY receptor_id, valid_at", {"r": run_id})
    for r in rows:
        r["issued_at"] = dt(r["issued_at"]); r["valid_at"] = dt(r["valid_at"])
    return rows


def save_run(run_id: str, scenario: str, issued_at: datetime, params: dict, k_mean: float, k_var: float, status: str):
    execute("""INSERT INTO model_runs (run_id, scenario, issued_at, params, k_mean, k_var, status, created_at)
               VALUES (:r, :s, :i, :p, :km, :kv, :st, :c)
               ON CONFLICT (run_id) DO UPDATE SET params = excluded.params, k_mean = excluded.k_mean,
               k_var = excluded.k_var, status = excluded.status""",
            {"r": run_id, "s": scenario, "i": ts(issued_at), "p": json.dumps(params), "km": k_mean,
             "kv": k_var, "st": status, "c": ts(datetime.now(UTC))})


def runs(scenario: str = "live", status: str = "ok", limit: int = 50) -> list[dict]:
    rows = query("""SELECT run_id, scenario, issued_at, params, k_mean, k_var, status FROM model_runs
                    WHERE scenario = :s AND status = :st ORDER BY issued_at DESC LIMIT :n""",
                 {"s": scenario, "st": status, "n": limit})
    for r in rows:
        r["issued_at"] = dt(r["issued_at"]); r["params"] = json.loads(r["params"] or "{}")
    return rows


def k_history(days: int = 30) -> list[float]:
    rows = query("""SELECT k_mean FROM model_runs WHERE scenario = 'live' AND status = 'ok'
                    ORDER BY issued_at DESC LIMIT :n""", {"n": days * 24})
    return [r["k_mean"] for r in rows if r["k_mean"] is not None]


# ---------- flow ----------
def upsert_flow(rows: list[dict]):
    if rows:
        execute("""INSERT INTO flow_daily (date, mgd, source) VALUES (:date, :mgd, :source)
                   ON CONFLICT (date) DO UPDATE SET mgd = excluded.mgd, source = excluded.source""",
                [{**r, "date": r["date"].isoformat() if isinstance(r["date"], date) else r["date"]} for r in rows])


def flow_upto(day: date, n: int = 60) -> list[dict]:
    return query("SELECT date, mgd, source FROM flow_daily WHERE date <= :d ORDER BY date DESC LIMIT :n",
                 {"d": day.isoformat(), "n": n})


def upsert_flow_event(e: dict):
    e = {k: e.get(k) for k in ("id", "published_at", "event_type", "location_text", "starts_at", "ends_at",
                                "expected_flow_mgd", "flow_delta_mgd", "peak_flow_mgd", "confidence",
                                "quote", "source_url", "entered_by")}
    for k in ("published_at", "starts_at", "ends_at"):
        e[k] = ts(dt(e[k])) if e[k] else None
    execute("""INSERT INTO flow_events VALUES (:id, :published_at, :event_type, :location_text, :starts_at,
               :ends_at, :expected_flow_mgd, :flow_delta_mgd, :peak_flow_mgd, :confidence, :quote,
               :source_url, :entered_by) ON CONFLICT (id) DO NOTHING""", e)


def flow_events() -> list[dict]:
    rows = query("SELECT * FROM flow_events ORDER BY starts_at DESC")
    for r in rows:
        for k in ("published_at", "starts_at", "ends_at"):
            r[k] = dt(r[k])
    return rows


# ---------- complaints / spills ----------
def upsert_complaints(rows: list[dict]):
    rows = [{**r, "received_at": ts(r["received_at"])} for r in rows]
    if rows:
        execute("""INSERT INTO complaints (record_number, received_at, nature, city, lat, lon)
                   VALUES (:record_number, :received_at, :nature, :city, :lat, :lon)
                   ON CONFLICT (record_number) DO UPDATE SET nature = excluded.nature""", rows)


def complaints(start: datetime, end: datetime, odor_only: bool = True) -> list[dict]:
    sql = "SELECT * FROM complaints WHERE received_at >= :a AND received_at < :b"
    if odor_only:
        sql += " AND nature LIKE '%Odor%'"
    rows = query(sql + " ORDER BY received_at", {"a": ts(start), "b": ts(end)})
    for r in rows:
        r["received_at"] = dt(r["received_at"])
    return rows


def replace_spills(rows: list[dict]):
    with engine().begin() as c:
        c.execute(text("DELETE FROM spills"))
        if rows:
            c.execute(text("""INSERT INTO spills VALUES (:site, :lat, :lon, :start_date, :end_date,
                              :event_type, :volume, :notes)"""), rows)


# ---------- fetch log / freshness ----------
def log_fetch(source: str, status: str, raw_path: str | None = None, detail: str | None = None):
    execute("""INSERT INTO source_fetches (source, fetched_at, status, raw_path, detail)
               VALUES (:s, :f, :st, :p, :d) ON CONFLICT (source, fetched_at) DO NOTHING""",
            {"s": source, "f": ts(datetime.now(UTC)), "st": status, "p": raw_path, "d": (detail or "")[:500]})


def freshness() -> dict[str, dict]:
    rows = query("""SELECT f.source, f.fetched_at, f.status, f.detail FROM source_fetches f
                    JOIN (SELECT source, max(fetched_at) m FROM source_fetches GROUP BY source) x
                    ON x.source = f.source AND x.m = f.fetched_at""")
    ok = query("SELECT source, max(fetched_at) m FROM source_fetches WHERE status = 'ok' GROUP BY source")
    last_ok = {r["source"]: dt(r["m"]) for r in ok}
    return {r["source"]: {"last_attempt": dt(r["fetched_at"]), "status": r["status"], "detail": r["detail"],
                          "last_ok": last_ok.get(r["source"])} for r in rows}


# ---------- subscriptions / alerts ----------
def add_subscription(s: dict):
    execute("""INSERT INTO subscriptions (id, contact, channel, language, receptor_id, created_at, token)
               VALUES (:id, :contact, :channel, :language, :receptor_id, :created_at, :token)""",
            {**s, "created_at": ts(s["created_at"])})


def has_subscription(contact: str, receptor_id: str) -> bool:
    return bool(query("SELECT 1 FROM subscriptions WHERE contact = :c AND receptor_id = :r", {"c": contact, "r": receptor_id}))


def remove_subscription(token: str) -> bool:
    return execute("DELETE FROM subscriptions WHERE token = :t", {"t": token}).rowcount > 0


def subscriptions() -> list[dict]:
    return query("SELECT * FROM subscriptions")


def alerts_sent_for(night: date) -> list[dict]:
    return query("SELECT * FROM alerts_sent WHERE night = :n", {"n": night.isoformat()})


def record_alert(subscription_id: str, night: date, run_id: str, kind: str, status: str):
    execute("""INSERT INTO alerts_sent (subscription_id, night, run_id, kind, sent_at, status)
               VALUES (:s, :n, :r, :k, :t, :st) ON CONFLICT DO NOTHING""",
            {"s": subscription_id, "n": night.isoformat(), "r": run_id, "k": kind,
             "t": ts(datetime.now(UTC)), "st": status})


# ---------- skill ----------
def save_skill(rows: list[dict]):
    rows = [{**r, "computed_at": ts(datetime.now(UTC))} for r in rows]
    if rows:
        execute("""INSERT INTO skill_scores (computed_at, method, metric, site_id, value, n, note)
                   VALUES (:computed_at, :method, :metric, :site_id, :value, :n, :note)
                   ON CONFLICT (method, metric, site_id) DO UPDATE SET value = excluded.value,
                   n = excluded.n, note = excluded.note, computed_at = excluded.computed_at""", rows)


def skill() -> list[dict]:
    return query("SELECT * FROM skill_scores ORDER BY method, metric, site_id")
