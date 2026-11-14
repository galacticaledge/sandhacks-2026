# Data status (spec 4, step 0: 2 PM go/no-go)

_Last updated: Sat 2026-11-14, ~2:15 PM PT_

## Historical H₂S: **GO (loaded 2026-11-14, no Bright Data, no Power BI)**

**Source used:** UCSD Resilient Shield's public yearly CSV files, in the same bucket and row format as the live feed.
Three plain GETs, no key, no login:

- `https://oss.resilientservice.mooo.com/resilentpublic/tijuana/sd_apcd_air/output/yearly/h2s/2024/apcd_h2s_2024.csv`
- `.../output/yearly/h2s/2025/apcd_h2s_2025.csv`
- `.../output/apcd_h2s_latest.csv` (2026 so far; Resilient Shield regenerates it daily, it ended 2026-11-12 23:00 PST when fetched)

**Collector:** `python -m collectors.h2s_history` (`--refresh` to re-download, `--summary` to only print counts).
Raw files are cached in `data/raw/h2s_history/`. Rows go into `h2s_readings` with `source = resilient_history`.
It is safe to rerun (upsert by site + hour) and it never overwrites `live_feed` rows.
Parser test: `collectors/tests/test_h2s_history.py`.

**What is in the database** (history + live feed, counted after the run on 2026-11-14):

| Site | Rows | Hours with a value | First value | Hours ≥ 30 ppb | Nights ≥ 30 ppb | Max ppb |
| --- | --- | --- | --- | --- | --- | --- |
| `ib_civic` | 16,240 | 14,068 | 2024-12-25 | 123 | 60 | 264.0 |
| `nestor_bes` | 18,136 | 17,286 | 2024-10-09 | 790 | 236 | 915.0 |
| `san_ysidro` | 23,957 | 19,187 | 2023-12-31 | 111 | 58 | 703.1 |

Total 58,333 rows, 2023-12-31 to 2026-11-14 12:00 PST. A "night" is 6 PM to 9 AM local, the same window as
`validate/replay.py`. The March 2026 spike named in the spec is there (Nestor: 114 hours ≥ 30 ppb in March 2026,
130 in April 2026).

**Timestamps (checked, not assumed):**

- `Date with time` is the **start** of the hourly average and carries its own UTC offset. We convert to UTC as is.
- Check 1, live feed: 71 site-hours overlap (Nov 12). All 71 values are identical at lag 0; shifting by 1 hour
  either way matches only 10 of about 70.
- Check 2, CARB AQMIS (state site, Pacific Standard Time, hour-start columns), from the researcher's cached pages:
  5 site-days in 2025 (Jan 15, Jul 15, Aug 15, Nov 15) match 24 of 24 hours at lag 0, including summer days.
- Check 3, SDAPCD's own air-data tool (researcher's cached JSON, standard time all year): 39,904 of 41,496
  shared hours are identical once both are in the same clock.
- Trap: the files pick the UTC offset by calendar day, so near a clock change the same wall-clock text can appear
  twice with different offsets (for example `2025-11-03T00:00` at `-07:00` and at `-08:00`). They are two different
  hours. Key rows on the UTC time, never on the local text. The test covers this.

**Limits:**

- All three monitors report together only from **Oct 2025 on** (plus Jan 2025 and May 2025, partly Apr and Jun 2025). Missing values:
  `ib_civic` Jul to Aug 2025; `san_ysidro` Feb to Mar 2025 and Jul to Sep 2025; all three 2025-12-30
  (falls between two files) and 48 hours in Feb 2026. Nestor is the only site with a nearly unbroken record.
- ≥ 30 ppb hours are mostly at Nestor. The three monitors do not spike together.
- `san_ysidro` before 2024-09-12 (about 5,400 hours, 29 of them ≥ 30 ppb) is in these files but **not** in SDAPCD's
  own tool, which starts that site on 2024-09-12. Treat those months as unconfirmed.
- Values are the raw daily exports. SDAPCD later finalised 2025: about 1,570 hours in 2025 differ from SDAPCD's final
  values, 24 of them by more than 5 ppb (example: IB 2025-04-21 02:00 PST is 264.0 here, 249.1 final). 59 of the
  1,024 hours ≥ 30 ppb in these files have no value in SDAPCD's tool (examples: San Ysidro 703.1 ppb on 2025-01-26, 21 Nestor
  hours in Jan 2026). Very high values (Nestor 915 ppb on 2026-06-02) were not validated.
- Blank `Result` or a `Qualifier` (`<`) is stored as a row with no value. Small negative values are kept as is.
- Not loaded, untested: `yearly/h2s/2023/apcd_h2s_2023.csv` (186 KB) and the parquet twins.

**Licence / credit:** the bucket's metadata files state no licence. Credit **UCSD Resilient Shield** (data files) and
**San Diego County Air Pollution Control District** (the measurements) wherever the history is shown.
[HUMAN] confirm reuse terms with Resilient Shield if the project goes beyond the hackathon.

**Other candidates (judged 2026-11-14):**

| Candidate | Verdict |
| --- | --- |
| SDAPCD air-data tool backend (`sdapcd.org/bin/apcdsd/apcd-air-data`, parameter 42402) | Has the same hourly data, with finalised 2025 values. Not used: it is an undocumented page backend, and it lacks Jan 2026 and most of Oct 2026. Used only as a cross-check from the researcher's cached files (not re-fetched by the judge). A possible later upgrade for 2025 values. |
| CARB AQMIS2 daily H₂S pages | Real, but 2025 only, 1 ppb steps, one page per day. Used only as a timezone cross-check from cached pages. |
| EPA AQS / AirNow | No San Diego H₂S monitors (AQS files) / no H₂S parameter (AirNow, untested claim). |
| UCSD Rico et al. deposit (doi:10.6075/J0DB8265) | 1-minute H₂S at a different Nestor site, 3 weeks in Sept 2024, CC BY 4.0. Not the county monitors. Not loaded. |
| Power BI dashboard via Bright Data (`collectors/powerbi_history.py`) | Not needed any more. Not run. No Bright Data credit spent. |

## Verified sources

| Source | Status | Notes |
| --- | --- | --- |
| Historical H₂S (Resilient Shield yearly CSVs) | ✅ loaded 11/14 | 58k hourly rows, 3 sites, see section above. `python -m collectors.h2s_history`. |
| Live H₂S (Resilient Shield) | ✅ verified 11/14 | 3 sites, ~60 h rolling. `level` missing on some rows and `Result` can be slightly negative; we derive the level from ppb. Polled ≤ every 15 min. |
| Odor complaints | ✅ verified | ~8k records back to 2023 (~6.5k odor); ~5.4k inside the South Bay box. |
| Spills by site | ✅ verified | 7 sites. |
| NWS forecast | ✅ verified | Gridpoint **SGX 58,7** (Nestor), raw gridpoint data: wind (km/h), direction, temp °C, sky cover %. |
| Past weather | ✅ verified | **KNRS** (Imperial Beach NOLF, 32.5631, −117.1100) via Iowa Environmental Mesonet ASOS. On the valley floor ~2 km from Nestor, so it sees the same nighttime drainage winds. Hourly with gaps; we interpolate. Fallback: KSDM (Brown Field). |
| River flow (USIBWC 11-0133.00) | ✅ verified 11/14 | `collectors/usibwc_flow.py`, plain httpx against the public USIBWC Water Data Portal export (accept disclaimer cookie, then `Export/DataSet`, dataset `Discharge.Best Available@11013300`, 15-min m³/s, provisional data). Averaged to daily means (UTC-8), converted to MGD (1 m³/s = 22.8245). 9,663 days stored, 2000-06-01 to 2026-11-14; raw zip cached in `data/raw/usibwc_flow/`. `model/inputs.py` reads it (source `gauge <date>`). Latest day is a partial-day mean. USGS NWIS has no data for 11013300 or 11013500. Bright Data is fallback only.
| USIBWC announcements | ✅ fetch verified, ⏳ extraction needs Gemini key | Verified 2026-11-14: `https://www.ibwc.gov/press-releases/` (static page, 217 items back to 2022) and its PDFs return 200 to plain httpx with a generic User-Agent; Bright Data is only a fallback. `collectors/announcements.py` caches the list, PDFs and extracted text under `data/raw/announcements/` (46 releases, 2025-02-05 to 2026-09-14, title keyword filter). Gemini step is skipped cleanly with no `GEMINI_API_KEY`; `flow_events` is still empty. Human: set `GEMINI_API_KEY`, rerun `python -m collectors.announcements` (uses cached text), then spot-check 10 events per spec 6. |
| UCSD research monitors | ⏭ skipped | Optional; not checked yet. |

## Geography decisions

- Saturn Blvd hotspot: longitude −117.0927 from OSM (Saturn Blvd alignment); river-channel latitude 32.5530 is
  estimated. **[HUMAN] confirm on satellite imagery** and edit `model/sources.yaml`.
- Receptors (`data/receptors.geojson`): 7 neighborhood centroids and 10 schools geocoded with Nominatim.
