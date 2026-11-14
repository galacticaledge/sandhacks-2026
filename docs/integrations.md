# Integrations and track coverage

Scope decisions (2026-11-14, with the team): **Neon cut** (redundant with Tiger Data), **Twilio SMS and ElevenLabs audio cut**.

| Track | Status | What it does | Files |
| --- | --- | --- | --- |
| Best Overall Hack | 🟢 working end to end on live data | Street-level 24 h H₂S forecast with uncertainty, Tonight list, replay, accuracy vs baselines, EN/ES | all |
| Bright Data: Data for Good | 🟡 code ready, **needs credentials** | Scraping Browser → SDAPCD Power BI history; Web Unlocker → USIBWC flow and press releases | `collectors/powerbi_history.py`, `usibwc_flow.py`, `announcements.py`, `collectors/common.py` |
| Tiger Data (TimescaleDB) | 🟡 code ready, **needs `DATABASE_URL`** | Single database: hypertables `h2s_readings`, `receptor_forecasts`, `weather_hourly`; continuous aggregates `nightly_peak_by_site`, `hours_over_30ppb_by_month`; app tables; replays isolated by `scenario` | `db/tiger_schema.sql`, `db/app_schema.sql`, `db/store.py` |
| Vultr (MLH) | 🟡 Dockerfile + compose ready, **needs a VM** | Runs API, scheduler, model runs and the SPA overnight | `Dockerfile`, `docker-compose.yml`, `api/scheduler.py` |
| Gemini API (MLH) | 🟡 code ready, **needs `GEMINI_API_KEY`** | Announcements → validated `flow_events` with verbatim quote; admin form fallback (`POST /api/admin/events`) | `extract/gemini_events.py` |
| GoDaddy Registry domain | 🔴 **[HUMAN]** register smellcast.us | Caddy in compose serves HTTPS when `DOMAIN` is set | `docker-compose.yml` |
| Neon | ✂️ cut | | |
| ElevenLabs | ✂️ cut | | |

Local dev runs on SQLite (`DATABASE_URL` empty) with the same tables.
