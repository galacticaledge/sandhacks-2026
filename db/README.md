# Database

One database: **Tiger Data** (TimescaleDB). Neon was cut on 2026-11-14 because it duplicated Tiger Data.

- `tiger_schema.sql`: hypertables `h2s_readings`, `receptor_forecasts`, `weather_hourly`, plus the continuous aggregates
  `nightly_peak_by_site` and `hours_over_30ppb_by_month`.
- `app_schema.sql`: relational app state (flow, flow events, runs, complaints, spills, subscriptions, alerts, skill).
- Replay isolation: rows written by replays carry `scenario = 'replay'` (this replaces Neon branches).
- With `DATABASE_URL` empty, the app uses `data/smellcast.sqlite` with the same tables. Hypertables and aggregates are Postgres-only.

`python -m db.init` creates everything (idempotent).
