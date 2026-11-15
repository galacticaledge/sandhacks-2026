# Validation

## Model skill (auto-generated: `data/skill.json`, Accuracy page)

Re-run with `python -m validate.calibration_job` then `python -m validate.replay` (the scheduler does this nightly
at 3:30 AM). Numbers below are from `data/skill.json`, computed Sat 2026-11-14 ~3:25 PM PT.

**Setup**

- History: 58,222 hourly readings, 2023-12-31 → 2026-11-12 (Resilient Shield yearly files + live feed), with real
  river flow (USIBWC gauge) and observed KNRS weather. 1,021 nights replayed through the full pipeline.
- Each night is the 5 PM forecast for 6 PM–9 AM, using only data available at 5 PM, **except weather: observed
  weather stands in for the forecast, which flatters skill.** Live skill with NWS forecasts will be lower.
- **Tuning** = nights before 2026-01-01 (calibration fitted here, in-sample). **Held out** = nights from
  2026-01-01 on, never used to fit or choose the model. All methods are scored on the same monitor-nights.
- "Orange night" = any hour ≥ 30 ppb at a monitor. Model alert rules follow spec 7: *likely* = P50 reaches
  30 ppb, *possible* = P90 reaches 30 ppb.

### Held-out results (2026, 901 monitor-nights, 168 orange)

| Method | MAE (log) | Category accuracy | Orange hit rate | False-alarm ratio |
| --- | --- | --- | --- | --- |
| **Smellcast, likely (P50)** | **0.585** | **68.8%** | 52.4% (88/168) | **20.0%** |
| Smellcast, possible (P90) | | | 93.5% (157/168) | 55.0% |
| Persistence (last night) | 0.620 | 65.8% | 60.5% (101/167) | 39.5% |
| Climatology (30-day hourly mean) | 0.702 | 55.3% | 43.5% (73/168) | 36.5% |

- **Fair comparison at the same number of alarms:** when the model raises as many alarms as persistence (167),
  it catches **69.0%** of orange nights with a **30.5%** false-alarm ratio, vs 60.5% / 39.5% for persistence.
  Ranking skill (AUC of the night peak for orange vs not): model **0.92**, persistence 0.86, climatology 0.85.
- **Spikes after a quiet night** (733 monitor-nights, 66 orange): persistence can never catch these (0/65).
  The model's likely alert catches 16 (24%, false-alarm ratio 30%); its possible alert catches 55 (83%, false-alarm
  ratio 72%). This is the case a reading-based alert misses by design.
- **Uncertainty is calibrated:** the observed night peak is under the forecast P90 on 90.8% of monitor-nights
  (target 90%), and 95.8% of hours.
- Tuning period (in-sample, 1,217 monitor-nights): MAE 0.652 vs 0.666 / 0.727, category accuracy 66.2% vs 60.6% /
  51.4%, hit rate 38.4% vs 49.7% / 20.9%, false-alarm ratio 34.6% vs 51.1% / 47.9% (model / persistence /
  climatology).

### By monitor (held out: hit rate / false-alarm ratio / category accuracy / MAE log)

| Monitor | Orange nights | Smellcast (likely) | Persistence | Climatology |
| --- | --- | --- | --- | --- |
| Nestor (Berry Elementary) | 102 | 67% / 15% / 64% / 0.71 | 71% / 29% / 63% / 0.80 | 72% / 37% / 52% / 0.95 |
| Imperial Beach Civic Ctr | 32 | 25% / 33% / 71% / 0.41 | 41% / 59% / 69% / 0.45 | 0% / – / 60% / 0.52 |
| San Ysidro | 34 | 35% / 33% / 72% / 0.64 | 48% / 53% / 66% / 0.61 | 0% / – / 55% / 0.63 |

### Leave one monitor out (held out)

Calibrate without one monitor's readings, then forecast that monitor as if it were an unmeasured street point.

| Held-out monitor | Hourly r (log) | MAE (log) | Likely: hit / false alarm | Persistence: hit / false alarm | Night peak under P90 |
| --- | --- | --- | --- | --- | --- |
| Imperial Beach | 0.54 | 0.43 | 28% / 40% | 41% / 59% | 97% |
| Nestor | 0.53 | 0.77 | 57% / 21% | 71% / 29% | 79% |
| San Ysidro | 0.39 | 0.87 | 88% / 77% | 48% / 53% | 99% |

(Before the history and real flow were loaded, these correlations were −0.11 to 0.19.) Persistence here still uses
the monitor's own readings, so it is not a fair street-level comparison; it is shown for scale.

### What this does and does not show

- The model beats both baselines on error, category accuracy, false alarms and ranking, on nights it never saw.
- At its default threshold it is **conservative**: fewer orange nights caught than persistence (52% vs 61%) but half
  the false alarms. The P90 "possible" alert catches 94% at the cost of many false alarms.
- Weakest at Imperial Beach and San Ysidro (few orange nights, 32–34 each). Without its own readings, San Ysidro
  is over-forecast (77% false alarms).
- Fitted parameters to review: temperature factor β ≈ 0 (no temperature effect found) and storm-water dilution
  exponent `dil_gamma` = 4.0, at its upper bound.
- Spatial check (odor complaints inside the forecast high area): only complaints with a street-level location count.
  ~91% of SDAPCD odor complaints (4,878 of 5,350) sit on one placeholder point used for several cities, and another
  88 on a second one; these are dropped (`replay.placeholder_points`). Each location counts once per night. The page
  shows a number only with ≥ 20 distinct locations inside mapped replay nights; today there are 4, so it says so.
- Replays are cached per night. A cached replay counts only if it was made with the current calibration
  (`replay.calibration_key`); otherwise it is recomputed, or left out of the scores and counted in
  `n_skipped_other_calibration`.
- All of this uses observed weather. A replay with archived NWS forecasts would measure true forecast skill.

## Gemini spot-check [HUMAN, 15 min]

Run `python -m collectors.announcements` once keys are in, then compare 10 extracted events against their PDFs.

| # | Release | Event type ok? | Times ok? | Flow numbers ok? | Quote verbatim? | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1–10 | | | | | | |
