-- Smellcast single database: Tiger Data (TimescaleDB / Postgres).
-- Neon was cut (2026-11-14): app tables live here too. Replays are isolated by `scenario`.
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS h2s_readings (
  observed_at TIMESTAMPTZ NOT NULL,   -- start of the hourly average
  site_id     TEXT NOT NULL,          -- ib_civic | nestor_bes | san_ysidro
  ppb         DOUBLE PRECISION,
  level       TEXT,                   -- green | yellow | orange | review
  source      TEXT NOT NULL,          -- live_feed | powerbi_history
  PRIMARY KEY (site_id, observed_at)
);
SELECT create_hypertable('h2s_readings', 'observed_at', if_not_exists => TRUE, migrate_data => TRUE);

CREATE TABLE IF NOT EXISTS receptor_forecasts (
  scenario    TEXT NOT NULL DEFAULT 'live',  -- live | replay
  issued_at   TIMESTAMPTZ NOT NULL,
  valid_at    TIMESTAMPTZ NOT NULL,
  receptor_id TEXT NOT NULL,
  p10 DOUBLE PRECISION, p50 DOUBLE PRECISION, p90 DOUBLE PRECISION,
  run_id      TEXT NOT NULL,
  PRIMARY KEY (scenario, receptor_id, issued_at, valid_at)
);
SELECT create_hypertable('receptor_forecasts', 'valid_at', if_not_exists => TRUE, migrate_data => TRUE);

CREATE TABLE IF NOT EXISTS weather_hourly (
  observed_at TIMESTAMPTZ NOT NULL, station TEXT NOT NULL, kind TEXT NOT NULL,  -- observed | forecast
  issued_at TIMESTAMPTZ, wind_ms DOUBLE PRECISION, wind_dir_deg DOUBLE PRECISION,
  temp_c DOUBLE PRECISION, cloud_frac DOUBLE PRECISION,
  PRIMARY KEY (station, kind, observed_at)
);
SELECT create_hypertable('weather_hourly', 'observed_at', if_not_exists => TRUE, migrate_data => TRUE);

-- Continuous aggregates (Accuracy page). Nights run 18:00 -> 18:00 local.
CREATE MATERIALIZED VIEW IF NOT EXISTS nightly_peak_by_site
WITH (timescaledb.continuous) AS
SELECT site_id,
       time_bucket('1 day', observed_at, 'America/Los_Angeles', "offset" => INTERVAL '18 hours') AS night,
       max(ppb) AS peak_ppb,
       count(*) FILTER (WHERE ppb >= 30) AS hours_orange
FROM h2s_readings GROUP BY site_id, night WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS hours_over_30ppb_by_month
WITH (timescaledb.continuous) AS
SELECT site_id,
       time_bucket('1 month', observed_at, 'America/Los_Angeles') AS month,
       count(*) FILTER (WHERE ppb >= 30) AS hours_over_30,
       count(*) AS hours_total
FROM h2s_readings GROUP BY site_id, month WITH NO DATA;

SELECT add_continuous_aggregate_policy('nightly_peak_by_site', start_offset => INTERVAL '120 days',
  end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '1 hour', if_not_exists => TRUE);
SELECT add_continuous_aggregate_policy('hours_over_30ppb_by_month', start_offset => INTERVAL '400 days',
  end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '6 hours', if_not_exists => TRUE);
