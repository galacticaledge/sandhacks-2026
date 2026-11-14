# Smellcast: a weather forecast for sewer gas

Experimental street-level forecast of hydrogen sulfide (H₂S) across the South Bay of San Diego for the next 24 hours,
with evening-before alerts in English and Spanish. **Not an official advisory**; official readings: SDAPCD.

Spec: [`SPEC.md`](SPEC.md). Status: [`docs/data_status.md`](docs/data_status.md), [`docs/integrations.md`](docs/integrations.md).

## Run locally

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

Demo fallback: `python -m scripts.make_demo` freezes a snapshot; `DEMO_MODE=1` serves it with no outside calls.

## Deploy (Vultr)

`docker compose up -d --build` with `.env` filled in (`DATABASE_URL` = Tiger Data, `DOMAIN` for HTTPS).
Logs: `logs/smellcast.log`. All jobs are idempotent and logged.

## Layout

`collectors/` live feeds + Bright Data · `extract/` Gemini flow events · `model/` emission, stability, puff, plume,
Kalman, ensemble, calibration (pure NumPy, tested) · `validate/` replay, baselines, metrics · `alerts/` rules,
verbatim SDAPCD guidance, EN/ES templates, email · `db/` Tiger Data schema + store · `api/` FastAPI + APScheduler ·
`web/` React + MapLibre + Recharts.

## Credits

Live H₂S: UCSD Resilient Shield and the San Diego County Air Pollution Control District (SDAPCD). Scientific basis:
Rico et al., *Science* (2025), Scripps / Prather lab. Weather: NWS, Iowa Environmental Mesonet. Basemap © OpenStreetMap
contributors, OpenFreeMap.
