# Smellcast: a weather forecast for sewer gas

Experimental street-level forecast of hydrogen sulfide (H₂S) across the South Bay of San Diego for the next 24 hours,
with evening-before alerts in English and Spanish. **Not an official advisory**; official readings: SDAPCD.

Spec: [`SPEC.md`](SPEC.md). Status: [`docs/data_status.md`](docs/data_status.md), [`docs/integrations.md`](docs/integrations.md).

## Run locally (Docker, everything local)

```bash
cp .env.example .env                      # leave DATABASE_URL / RESEND_API_KEY empty
docker compose up -d --build
```

- App: http://localhost:8000
- TimescaleDB (local Tiger Data): `postgresql://smellcast:smellcast@localhost:5433/smellcast`
- Mailpit inbox for alert emails: http://localhost:8025

Run one-off jobs inside the stack, e.g. `docker compose exec smellcast python -m model.run`.
Bright Data and Gemini are hosted APIs with no local equivalent; without keys those collectors are skipped.

## Run locally (bare Python)

```bash
uv venv --python 3.11 .venv && uv pip install --python .venv -r requirements.txt
cp .env.example .env                      # empty DATABASE_URL -> local SQLite
.venv/bin/python -m db.init
.venv/bin/python -m collectors.h2s_feed && .venv/bin/python -m collectors.nws && .venv/bin/python -m collectors.weather_archive
.venv/bin/python -m model.run             # one live forecast (~35 s)
(cd web && npm ci && npm run build)
.venv/bin/uvicorn api.main:app --port 8000   # starts the scheduler too (SCHEDULER=0 to disable)
```

Tests: `.venv/bin/python -m pytest -q`

Seed a live database (history, weather, river flow, complaints, Gemini flow events, calibration, and map replays
of the worst nights, with the worst one featured on the Replay page). Uses `$DATABASE_URL`; safe to rerun:

```bash
.venv/bin/python -m scripts.seed                      # all steps (~30 min, mostly the bad-night maps)
.venv/bin/python -m scripts.seed --skip flow reports  # leave steps out; --only replays to redo just the maps
docker compose exec smellcast python -m scripts.seed  # inside a running container
```

In Docker/Podman, set `SEED=1` in `.env` instead: the app container seeds itself once in the background on its
first start (log in `logs/seed.log`, marker in `data/.seeded.json`). `SEED=small` caps the Replay list at the 5 worst nights; `SEED=always` reseeds on every start;
`SEED_ARGS="--skip reports --nights 3"` passes options through.

The `flow` step accepts the USIBWC Water Data Portal disclaimer. The `reports` step spends Bright Data credit and
runs only when the Bright Data and Gemini keys are set. `--score` also replays and scores every night (hours).

Demo fallback: `python -m scripts.make_demo` freezes a snapshot whose Replay list is the 5 worst nights (plus news
reports if seeded; `--trim` keeps only the data around those nights); `DEMO_MODE=1` serves it with no outside calls.

## Deploy (Vultr)

`docker compose --profile https up -d --build` with `.env` filled in (`DATABASE_URL` = Tiger Data,
`RESEND_API_KEY`, `DOMAIN` for HTTPS). The local TimescaleDB and Mailpit containers still start but go unused.
Logs: `logs/smellcast.log`. All jobs are idempotent and logged.

## Layout

`collectors/` live feeds + Bright Data · `extract/` Gemini flow events · `model/` emission, stability, puff, plume,
Kalman, ensemble, calibration (pure NumPy, tested) · `validate/` replay, baselines, metrics · `alerts/` rules,
verbatim SDAPCD guidance, EN/ES templates, email · `db/` Tiger Data schema + store · `api/` FastAPI + APScheduler ·
`web/` React + MapLibre + Recharts.

## Credits

Live H₂S: UCSD Resilient Shield and the San Diego County Air Pollution Control District (SDAPCD). Scientific basis:
Rico et al., *Science* (2025), Scripps / Prather lab. Weather: NWS, Iowa Environmental Mesonet. Basemap © OpenStreetMap
contributors, OpenFreeMap. San Diego County and City of Imperial Beach boundaries: U.S. Census Bureau TIGERweb (public domain). Community planning areas: City of San Diego Open Data Portal (Community Planning Districts).
