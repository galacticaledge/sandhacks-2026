# South Bay Sewer-Gas Forecast — Build Spec for an AI Agent

Nov 14, 2026 · @Chris

## 0. How to use this spec

Give this document to your coding agent (Claude Code, Cursor, etc.) as its first message, or commit it as `SPEC.md` and tell the agent to follow it. It is the source of truth for what to build. Items marked **\[HUMAN\]** need an answer or an action from a person: the agent lists them up front and keeps working around them.

## 1. Product summary

Build a web service that **forecasts hydrogen sulfide (H₂S, "sewer gas") at street level across the South Bay of San Diego for the next 24 hours**, and warns each neighborhood and school the evening before a spike, in English and Spanish.

**Already solved by others (don't rebuild):** measuring H₂S (three county air-district monitors, plus two UCSD research monitors), showing it on a map (the county / UCSD Resilient Shield dashboard), and sending a text after levels pass 30 ppb.

**What we build (not solved):**

1. **A forecast, not a report.** Peaks happen at night when wind dies down, so an alert that goes out after a reading is high arrives too late.
2. **Street-level estimates between the three monitors**, from a physics model of how gas spreads from the river.
3. **Automatic alerts the evening before**, with no human in the loop.
4. **Proof that it works:** replays of past spikes, scored against what the monitors actually measured.

**Pipeline:** collect (live feeds + Bright Data) → store (Neon + Tiger Data) → model (emission + dispersion + calibration) → forecast (24 h, hourly) → serve (FastAPI + React map) → alert.

**Design principles:**

1. The forecast is a physics model tuned to real measurements. LLMs never produce a concentration number.
2. Every forecast shows its inputs (flow, wind, calibration) and its uncertainty.
3. We complement official sources: link to the county air district's guidance and alerts everywhere, and never present our output as an official advisory.
4. A working end-to-end path beats breadth. Build the P0 path first (section 11).

## 2. Hard constraints

**Timebox (hard):**

- No git commits after **Sun Nov 15, 12:00 PM PT**. Pivoting the existing repo is fine.
- **2:00 PM Saturday: go/no-go on historical H₂S data** (section 4). Everything downstream depends on it.
- **Feature freeze: Sun 10:00 AM PT.** After that, only bug fixes and the demo-mode snapshot.
- The team is offline Sat 9 PM to Sun 7 AM. Ingestion, model runs and replays must run unattended on the Vultr server, with logs.

**Engineering:**

- All secrets go in `.env`, which is listed in `.gitignore`; commit a `.env.example` with variable names only.
- Python 3.11 + FastAPI + NumPy/SciPy for the backend and model; a React SPA (Vite + TypeScript) built to static files that FastAPI serves; MapLibre for the map.
- Cache every raw response from every source, with its fetch time. Never refetch history you already have.
- `DEMO_MODE=1` serves a seeded snapshot (including one replayed spike) if any outside source fails during a live presentation.

**Data etiquette:**

- The live H₂S feed is published by UCSD's Resilient Shield project. Poll it at most once every 15 minutes, cache it, and credit Resilient Shield and the San Diego County Air Pollution Control District (SDAPCD) on every page that shows the data.
- Credit the Scripps / Prather lab research (Rico et al., *Science*, 2025) on the About page as the scientific basis.
- Bright Data budget: **$100 of credits**. Log each job's cost in `docs/credits.md`, and ask a human before any single job estimated above $15.

**Health-messaging guardrails:**

- Every page and alert says it's an **experimental forecast, not an official advisory**, and links to SDAPCD's H₂S page and alert sign-up.
- Use SDAPCD's own color levels and actions (section 7). Never invent health advice; quote the county guidance.
- Always show uncertainty (a range or confidence level), and never claim a location is "safe".
- Alert subscriptions store only what's needed (contact + neighborhood + language), and offer one-click unsubscribe.

## 3. Functional requirements

**Users:**

- **Residents** of Nestor, Imperial Beach, San Ysidro, Egger Highlands and nearby neighborhoods: "Should I close the windows and run the purifier tonight?"
- **Schools and clinics:** "Will tomorrow morning's drop-off or recess be in the yellow or orange range?"
- **Advocates, journalists, agencies:** "How often, where, and under what conditions do spikes happen, and could they have been predicted?"

**Core screens:**

1. **Forecast map:** a South Bay map with the three county monitors (live values), the modeled street-level concentration as a colored layer, and a 24-hour time slider in hourly steps. The river hotspot is marked.
2. **Tonight:** a list of neighborhoods and schools with the forecast peak level, the hour of the peak, the color category, and a confidence label.
3. **Replay:** pick a past date. The map shows the forecast as it would have been issued at 5 PM the evening before, next to what the monitors actually recorded.
4. **Accuracy:** skill scores from the replays, compared with a simple "tomorrow night will look like last night" baseline.
5. **Alerts sign-up:** neighborhood or school + language (English or Spanish) + channel.
6. **About:** method, data sources and credits, limitations, links to official guidance.

**Primary user flows (each must work end to end):**

1. **See tonight's risk:** open the site, see tonight's forecast map and the "Tonight" list, and drag the slider through the night.
2. **Check a place:** click any point or search an address to get its hourly forecast chart for the next 24 hours, with the uncertainty band.
3. **Replay a spike:** choose a past spike date and compare the forecast with the observed readings at each monitor.
4. **Get warned:** subscribe for a neighborhood, and receive the evening alert when the forecast crosses a threshold (section 7).

## 4. Data sources and ingestion

Live H₂S, odor complaints and spills come from verified public JSON feeds. Historical H₂S, river flow and the commission's announcements need Bright Data. Weather comes from free government APIs.

| Source | What we get | How | Status |
| --- | --- | --- | --- |
| Live H₂S, 3 county monitors | Hourly ppb for `IB CIVIC CTR`, `NESTOR - BES` (Berry Elementary), `SAN YSIDRO`, with lat/lon and color level; rolling \~60 hours | `GET https://oss.resilientservice.mooo.com/resilentpublic/tijuana/sd_apcd_air/output/hs2_lastday.records.json` every 15 min | **Verified** Nov 14 (fields: `SiteName`, `Latitude`, `Longitude`, `Date with time`, `Result`, `level`) |
| Odor complaints | Points with time | `.../resilentpublic/latest/tijuana/sd_complaints/complaints.geojson` | **Verified** |
| Sewage spills by site | Points with latest event | `.../resilentpublic/tijuana/ibwc/output/spills_last_by_site.geojson` | **Verified** |
| Historical H₂S (months) | Hourly history for the 3 monitors | SDAPCD's Power BI dashboard, linked from its H₂S monitoring page; **Bright Data Scraping Browser** captures the dashboard's data responses | **Unverified: 2 PM go/no-go** |
| River flow at the border | Daily (or finer) flow in MGD at the Tijuana River gauge | USIBWC Water Data Portal; Bright Data Web Unlocker, or the portal's own CSV export if it has one | To verify |
| Commission announcements | Pump shutdowns, flow spikes, repairs | USIBWC press-release PDFs on ibwc.gov; Bright Data Web Unlocker → Gemini (section 6) | To verify |
| Weather forecast | Hourly wind speed and direction, temperature, sky cover, 48 h | National Weather Service API (`api.weather.gov`, gridpoint hourly forecast for Nestor) | Standard, free |
| Past weather | Hourly wind, temperature, cloud for replays | Nearest airport weather station archive (e.g. Iowa Environmental Mesonet ASOS download); **\[agent: pick the closest station to the river valley and record its ID\]** | Standard, free |
| UCSD research monitors (optional) | 1-minute H₂S at Nestor (Leon Ave) and the Imperial Beach pier | `airborne.ucsd.edu/h2s-2/`; use only if the plot is backed by a data file; skip if it's just an image | Optional |

**Step 0, the 2 PM go/no-go:** open SDAPCD's H₂S monitoring page, follow the Power BI dashboard link, and try to extract at least **3 months of hourly history** for all three monitors (Bright Data Scraping Browser: load the report, change the date filter, and record the data responses it loads). Write the result in `docs/data_status.md`.

- **Go:** store the history, and replays (section 5) use real past spikes, such as the March 2026 heat-wave spike.
- **No-go:** keep collecting the live feed from now on, validate on the odor complaints and whatever days we capture, and say so plainly on the Accuracy page. **\[HUMAN\]** may also email SDAPCD to request data, but don't wait for an answer.

**Ingestion jobs** (run on the Vultr server with APScheduler, each idempotent and logged):

1. `poll_h2s()` every 15 min → upsert readings keyed by site + hour.
2. `poll_complaints()` and `poll_spills()` every 30 min.
3. `fetch_flow()` daily, plus whenever a new announcement appears.
4. `fetch_announcements()` every 6 h → Gemini extraction → `flow_events`.
5. `fetch_nws_forecast()` hourly; `backfill_weather(start, end)` once for the replay window.
6. `run_forecast()` hourly, plus a guaranteed **5:00 PM run** that feeds the evening alerts.

## 5. The prediction model

The model treats the river hotspot as a smokestack. River flow and temperature set how much gas it releases; wind and nighttime air stillness carry and pool it; and hourly monitor readings keep the release rate honest. This follows the published finding that an air trajectory model reproduced observed H₂S only when meteorology and river flows were both represented (Rico et al., *Science*, 2025). Put it all in `/model`, as pure NumPy functions with unit tests.

**1. Sources.** The main source is the turbulent hotspot at the **Saturn Boulevard river crossing**. **\[agent: take its coordinates from a map and record them in `model/sources.yaml`.\]** Allow up to 3 configurable point sources along the river channel; each gets a share of the total release that calibration fits.

**2. Emission rate per hour** (grams per second):

```latex
E_t = k_t \cdot Q_t^{\alpha} \cdot e^{\beta (T_t - T_{ref})}
```

Q is river flow in million gallons per day, T is air temperature (a stand-in for water temperature), and T\_ref is 15 °C. Start with α = 1 and β = 0.05 per °C; k is fitted (step 4). Flow comes from the gauge, carried forward when it's missing, and adjusted by `flow_events` (section 6).

**3. Dispersion to a street-level grid.**

- Grid: 50 m cells over the box lat 32.535–32.600, lon −117.140 to −117.030 (about 10 × 7 km). Concentration at 1.5 m above ground.
- **Primary: a Gaussian puff model.** Release a puff from each source every 10 minutes, move it with the hourly wind, grow its spread with travel time, and sum the puffs at each cell. Puffs handle wind shifts and near-calm nights, which is when peaks happen.
- Spread rates come from Pasquill–Gifford stability classes A to F, set from wind speed, time of day and cloud cover (simplified Turner method). Clear, calm nights get class E or F: slow spread, high concentrations.
- Floor wind speed at 0.5 m/s. Add a fitted background level per monitor, roughly 0.3–0.6 ppb.
- **Fallback** if the puff model isn't ready by 5 PM: a steady-state Gaussian plume per hour, same stability classes.
- Convert units with ppb = µg/m³ × 24.45 / 34.08.

**4. Calibration and data assimilation.**

- **Offline:** fit α, β, the source shares and a base log k by least squares on log(C + 1) at the three monitors over the training window.
- **Online:** a Kalman filter on log k\_t, treated as a random walk, updated each hour with the newest readings. This soaks up things we can't observe, such as a pump failure the commission hasn't announced yet.

**5. Forecast (next 24 h, hourly).** Use NWS forecast wind, temperature and cloud cover. Carry flow forward, adjusted by announced `flow_events`. Relax k back toward its 30-day median over 12 hours.

**6. Uncertainty.** Run 20 ensemble members: wind direction ±15°, wind speed ±30%, and log k drawn from the filter's variance. Store the 10th, 50th and 90th percentiles per cell and hour. The confidence label comes from the spread: high when P90/P50 < 2, low when it's > 4.

**7. Validation (powers the Accuracy page and the replays).**

- **Replay:** for every day in the history, issue the 5 PM forecast using only data available at that time. Past weather comes from the station archive standing in for the forecast; label these results "with observed weather", since they flatter real forecast skill.
- **Leave-one-monitor-out:** calibrate on two monitors and predict the third.
- **Metrics:** for nights with any hour at or above 30 ppb (orange) at a monitor, report the hit rate and false-alarm rate. Also report green/yellow/orange category accuracy, and mean absolute error on a log scale.
- **Baselines we must beat:** persistence ("tonight looks like last night") and climatology (the average for each hour of the day). Report the comparison honestly, even if we lose.
- **Spatial check:** odor complaints should fall inside the forecast high-concentration area more often than chance.

## 6. Gemini: turning announcements into flow events

The commission often announces flow changes before the gauge shows them: pump-station shutdowns, broken collectors, repairs, diversions. Gemini reads those announcements and turns them into structured events the forecast can use. It never produces a concentration.

- **Input:** the text of each new USIBWC press release or stakeholder statement (PDF → text), fetched through Bright Data.
- **Model:** Gemini Flash-Lite in JSON mode, validated with a pydantic schema.
- **Schema:** `{published_at, event_type: [pump_shutdown | collector_failure | repair | diversion | storm | other], location_text, starts_at, ends_at|null, expected_flow_mgd|null, flow_delta_mgd|null, peak_flow_mgd|null, confidence: 0-1, quote}`. `quote` is the exact sentence the values came from, shown in the UI as evidence.
- **Use in the model:** an active event with `expected_flow_mgd` or `flow_delta_mgd` overrides the carried-forward flow for its time window. Events with confidence below 0.6 are shown on the timeline but not used.
- **Check:** run it over the 2025–2026 releases and spot-check 10 against the PDFs by hand (**\[HUMAN\]**, 15 minutes). Record the results in `docs/validation.md`.
- **Fallback:** if Gemini is down, events can be entered by hand through a small admin form.

## 7. Alerts

The 5:00 PM forecast run decides the evening alerts automatically, using the county air district's own color levels so our language matches official guidance.

| Level | 1-hour H₂S | Source of the level and its actions |
| --- | --- | --- |
| Green | under 5 ppb | SDAPCD Community H₂S Guidance |
| Yellow | 5 to 29.9 ppb | SDAPCD Community H₂S Guidance |
| Orange | 30 ppb or higher | SDAPCD Community H₂S Guidance; California's 1-hour standard is 30 ppb |
| Multi-agency review | 200 ppb or higher | SDAPCD Community H₂S Guidance |

**Rules:**

- **Likely orange:** the median (P50) forecast reaches 30 ppb or more in any hour from 6 PM to 9 AM for the subscriber's neighborhood or school. Send at 5:15 PM.
- **Possible orange:** only the P90 forecast reaches 30 ppb. Send as a "possible" alert with a low-confidence label.
- **Update:** if the 11 PM run raises a neighborhood to likely orange and no alert went out, send one. Never send more than 2 alerts per subscriber per night.
- **Every alert includes:** the expected peak window, the level, the confidence, the county's recommended actions (quoted from SDAPCD guidance), the "experimental forecast" disclaimer, and a link to the official SDAPCD page.

**Languages:** fixed English and Spanish templates with placeholders; no AI-written alert text. **\[HUMAN: a fluent Spanish speaker on the team reviews the Spanish templates.\]**

**Channels:**

- **P0:** the "Tonight" page plus email (any transactional email API with a free tier).
- **P1:** SMS via a Twilio trial account **\[HUMAN: create the account and verify the demo phone numbers\]**.
- **P2, ElevenLabs:** a nightly 30-second audio bulletin in English and Spanish, generated from the same template text with ElevenLabs text-to-speech. It plays on the Tonight page and is linked from the SMS, for residents who prefer listening to reading.

## 8. Architecture and stack

One Python service on Vultr runs ingestion, the model and the API, and serves the React app. Readings and forecasts at fixed points go to Tiger Data; everything else goes to Neon; forecast grids are stored as files.

| Layer | Choice | Responsibility |
| --- | --- | --- |
| Collectors | `httpx` for the public JSON feeds and the NWS API; **Bright Data Scraping Browser** (Playwright over CDP) for the Power BI history; **Bright Data Web Unlocker** for the USIBWC data portal and press releases | Raw responses cached with fetch time |
| Extraction | **Gemini** Flash-Lite, JSON mode | Announcements → `flow_events` (section 6) |
| Time-series store | **Tiger Data** (TimescaleDB) | `h2s_readings` and `receptor_forecasts` as hypertables; continuous aggregates for nightly peak per site and hours above 30 ppb per month |
| App store | **Neon** Postgres | Sites, sources, flow, flow events, model runs, subscriptions, alerts sent, complaints; **one branch per replay scenario** so replays never touch live data |
| Model | NumPy / SciPy | Emission, puff dispersion, Kalman calibration, ensemble (section 5) |
| Grid output | Float32 arrays + colored PNG overlays per hour, in `/data/forecasts/{run_id}/` | Fast map rendering without millions of database rows |
| API + jobs | FastAPI + APScheduler in Docker Compose on a **Vultr** VM | REST endpoints, scheduled jobs, serves the SPA |
| Frontend | React (Vite + TypeScript) + MapLibre GL + Recharts | Map, Tonight, Replay, Accuracy, Alerts, About |
| Alerts | Email API (P0), Twilio SMS (P1), **ElevenLabs** audio bulletin (P2) | Section 7 |
| Domain | **GoDaddy Registry** domain via the MLH offer | Public URL pointing at the Vultr server |

**Why two databases:** sensor readings and point forecasts are a true time-series workload. Every hourly run writes 24 hours × 3 percentiles × every neighborhood, school and monitor, and the Accuracy page queries hourly and nightly aggregates over months. Tiger Data's hypertables and continuous aggregates handle that well. Neon holds the relational app state and gives each replay scenario an isolated branch. **Fallback:** if Tiger Data becomes a time sink, use plain Neon tables (section 11).

**Repo layout:**

```
/collectors   h2s_feed.py, complaints.py, spills.py, powerbi_history.py, usibwc_flow.py, announcements.py, nws.py, weather_archive.py
/extract      gemini_events.py (schema + prompt)
/model        sources.yaml, emission.py, stability.py, puff.py, plume.py, calibrate.py, kalman.py, ensemble.py, tests/
/validate     replay.py, metrics.py, baselines.py
/alerts       rules.py, templates/{en,es}/, send_email.py, send_sms.py, audio_bulletin.py
/db           tiger_schema.sql, neon_schema.sql, branches.md
/api          main.py (FastAPI), routes/, scheduler.py
/web          React app (Vite); npm run build → web/dist, served by FastAPI
/data         receptors.geojson (neighborhoods, schools), forecasts/
/docs         data_status.md, validation.md, integrations.md, credits.md
```

## 9. Data model, API and frontend

**Tiger Data:**

```sql
CREATE TABLE h2s_readings (
  observed_at TIMESTAMPTZ NOT NULL,   -- start of the hourly average
  site_id     TEXT NOT NULL,          -- ib_civic | nestor_bes | san_ysidro
  ppb         DOUBLE PRECISION,
  level       TEXT,                   -- green | yellow | orange
  source      TEXT NOT NULL,          -- live_feed | powerbi_history
  PRIMARY KEY (site_id, observed_at)
);
SELECT create_hypertable('h2s_readings', 'observed_at');

CREATE TABLE receptor_forecasts (
  issued_at   TIMESTAMPTZ NOT NULL,
  valid_at    TIMESTAMPTZ NOT NULL,
  receptor_id TEXT NOT NULL,          -- monitor, neighborhood centroid, or school
  p10 DOUBLE PRECISION, p50 DOUBLE PRECISION, p90 DOUBLE PRECISION,
  run_id      TEXT NOT NULL,
  PRIMARY KEY (receptor_id, issued_at, valid_at)
);
SELECT create_hypertable('receptor_forecasts', 'valid_at');
-- continuous aggregates: nightly_peak_by_site, hours_over_30ppb_by_month
```

**Neon:** `sites`, `receptors` (neighborhoods and schools from `receptors.geojson`), `sources`, `flow_daily(date, mgd, source)`, `flow_events` (section 6 schema), `weather_hourly`, `model_runs(run_id, issued_at, params jsonb, k_mean, k_var, status)`, `complaints`, `spills`, `subscriptions(id, contact, channel, language, receptor_id, created_at)`, `alerts_sent`, `skill_scores`. Branches: `main`, plus `replay-<yyyy-mm>` per replay window.

**API (FastAPI):**

| Method + path | Returns |
| --- | --- |
| `GET /api/now` | latest readings per monitor, latest run id, data freshness for every source |
| `GET /api/forecast/{run_id}/grid/{hour}.png` | colored overlay image for one forecast hour, plus its bounds |
| `GET /api/forecast/latest/point?lat=&lon=` | 24-hour P10/P50/P90 series at a point |
| `GET /api/tonight` | each receptor's peak level, peak hour, confidence (from the 5 PM run) |
| `GET /api/replay?date=` | the forecast issued the evening before, plus observed readings for that night |
| `GET /api/skill` | metrics vs persistence and climatology (section 5) |
| `GET /api/events` | flow events with their quoted evidence |
| `POST /api/subscribe`, `GET /api/unsubscribe/{token}` | alert subscriptions |
| `GET /api/bulletin/{date}/{lang}.mp3` | the audio bulletin (P2) |

The SPA is served by FastAPI from `web/dist`: register `/api/*` routes first, mount static assets, then add a catch-all that returns `index.html`.

**Frontend pages:**

- **Map:** MapLibre with the forecast PNG overlay, monitor markers showing live values, the hotspot marker, recent odor complaints as small dots, a 24-hour slider, a legend with SDAPCD colors, and a "last updated" freshness chip.
- **Point panel:** click anywhere for its 24-hour chart with the P10–P90 band and the 30 ppb line.
- **Tonight:** a sortable list of neighborhoods and schools, the audio bulletin player (P2), and a language toggle.
- **Replay:** a date picker, the map side by side with observed values, and a per-monitor chart of forecast vs observed.
- **Accuracy:** metric cards and a chart against the two baselines.
- **About:** method, credits, limitations, official links.

English and Spanish UI strings throughout; colorblind-safe palette with icons alongside colors.

## 10. Required integrations and track coverage

We enter **8 tracks**. Each integration does real work in the running product. P0 = must ship, P1 = should ship, P2 = only if ahead of schedule.

| Track | Integration and what it must do | Code | Priority |
| --- | --- | --- | --- |
| Best Overall Hack | The whole system: a street-level forecast with measured skill on a real, local public-health problem | all | P0 |
| Bright Data: Data for Good | Scraping Browser extracts the Power BI H₂S history; Web Unlocker collects USIBWC flow data and press releases | `/collectors/powerbi_history.py`, `usibwc_flow.py`, `announcements.py` | P0 |
| Neon | App state, subscriptions, model runs; **a branch per replay scenario** | `/db/neon_schema.sql`, `/api` | P0 |
| Vultr (MLH) | Hosts the API, scheduler, model runs and the SPA; runs overnight | `docker-compose.yml`, `/api/scheduler.py` | P0 |
| Gemini API (MLH) | Turns commission announcements into structured flow events (section 6) | `/extract/gemini_events.py` | P1 |
| Tiger Data (MLH) | Hypertables for readings and point forecasts; continuous aggregates for nightly peaks and hours over 30 ppb | `/db/tiger_schema.sql` | P1 |
| GoDaddy Registry domain (MLH) | **smellcast.us** (checked available at GoDaddy on Nov 14 at $7.99 for the first year); register through the MLH offer and point it at Vultr | DNS, **\[HUMAN\]** | P1 |
| ElevenLabs | Nightly English and Spanish audio bulletin from the alert templates | `/alerts/audio_bulletin.py` | P2 |

**Not entering:** Solana (nothing meaningful to anchor) and the SpaceX AI track (requirements unknown).

**Product name:** **Smellcast**, "a weather forecast for sewer gas." Use it in the UI title and the About page. **\[HUMAN: register the domain now; availability can change.\]**

**Rules for the agent:**

- Keep `docs/integrations.md` updated with each integration's status and the files that implement it.
- Never let a P1 or P2 integration block a P0. If one is stuck for more than 45 minutes, stop and ask a human whether to cut it.
