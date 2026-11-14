# Data status (spec 4, step 0: 2 PM go/no-go)

_Last updated: Sat 2026-11-14, ~1:25 PM PT_

## Historical H₂S: **PENDING (needs a human decision + Bright Data credentials)**

- Found the dashboard: SDAPCD's TJRV air-quality monitoring page
  (`https://www.sdapcd.org/content/sdapcd/about/tj-river-valley/tjrv-air-quality-monitoring.html`) embeds a **public
  Power BI report on the US Government cloud** (`app.powerbigov.us/view?r=…`, cluster `wabi-us-gov-iowa-api.analysis.usgovcloudapi.net`).
- The report's data model has a `Sharepoint-Data` table with `DATE`, `TIME`, `DATETIME`, `Location`, `ppB` (hourly,
  all three monitors) behind a line chart and a date slicer, so months of hourly history are in the model.
- The coding agent's attempt to query the report's data endpoint **directly** was blocked by a safety check
  (it was judged as possibly unauthorized access). We did **not** work around it.
- `collectors/powerbi_history.py` implements the spec's intended path: **Bright Data Scraping Browser** loads the report like a
  visitor, changes the report's own date slicer, and records the `querydata` responses the page loads. The responses are cached raw in
  `data/raw/powerbi_history/` and decoded (Power BI DSR format, unit-tested).
- **To run:** a human confirms this use is OK, puts `BRIGHTDATA_SCRAPING_BROWSER_WSS` in `.env`, then
  `python -m collectors.powerbi_history --months 6`. Record the job's cost in `docs/credits.md`.
- **Alternative [HUMAN]:** email SDAPCD to request the hourly H₂S history (don't wait for a reply).

**If no-go:** we keep collecting the live feed every 15 minutes from Sat Nov 14 (the feed gives ~60 h back, so the
history starts Thu Nov 12) and validate on that plus odor complaints. The Accuracy page states this plainly.

## Verified sources

| Source | Status | Notes |
| --- | --- | --- |
| Live H₂S (Resilient Shield) | ✅ verified 11/14 | 3 sites, ~60 h rolling. `level` missing on some rows and `Result` can be slightly negative; we derive the level from ppb. Polled ≤ every 15 min. |
| Odor complaints | ✅ verified | ~8k records back to 2023 (~6.5k odor); ~5.4k inside the South Bay box. |
| Spills by site | ✅ verified | 7 sites. |
| NWS forecast | ✅ verified | Gridpoint **SGX 58,7** (Nestor), raw gridpoint data: wind (km/h), direction, temp °C, sky cover %. |
| Past weather | ✅ verified | **KNRS** (Imperial Beach NOLF, 32.5631, −117.1100) via Iowa Environmental Mesonet ASOS. On the valley floor ~2 km from Nestor, so it sees the same nighttime drainage winds. Hourly with gaps; we interpolate. Fallback: KSDM (Brown Field). |
| River flow (USIBWC 11-0133.00) | ⚠️ to verify | `collectors/usibwc_flow.py` uses the standard Aquarius WebPortal CSV export through Bright Data Web Unlocker; URL pattern unverified. Until it works, flow = `DEFAULT_FLOW_MGD` (35), labelled "assumed default" in every forecast. |
| USIBWC announcements | ⚠️ to verify | List page URL (`USIBWC_NEWS_URL`) unverified; needs Bright Data + Gemini keys. |
| UCSD research monitors | ⏭ skipped | Optional; not checked yet. |

## Geography decisions

- Saturn Blvd hotspot: longitude −117.0927 from OSM (Saturn Blvd alignment); river-channel latitude 32.5530 is
  estimated. **[HUMAN] confirm on satellite imagery** and edit `model/sources.yaml`.
- Receptors (`data/receptors.geojson`): 7 neighborhood centroids and 10 schools geocoded with Nominatim.
