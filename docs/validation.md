# Validation

## Model skill (auto-generated: `data/skill.json`, Accuracy page)

Re-run with `python -m validate.replay` (the scheduler does this nightly at 3:30 AM).

As of Sat 2026-11-14 1:25 PM: history = Nov 12–14 from the live feed only (no Power BI history yet).
3 nights replayed, scored on the **same 6 monitor-nights** for all methods. No orange nights, so hit rate and
false-alarm ratio can't be computed yet.

| Method | MAE (log) | Category accuracy |
| --- | --- | --- |
| Smellcast (observed weather) | 0.48 | 67% |
| Persistence | 0.56 | 67% |
| Climatology | 0.61 | 67% |

This sample is far too small to claim skill. The real test needs the historical spikes (see `data_status.md`).

## Gemini spot-check [HUMAN, 15 min]

Run `python -m collectors.announcements` once keys are in, then compare 10 extracted events against their PDFs.

| # | Release | Event type ok? | Times ok? | Flow numbers ok? | Quote verbatim? | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1–10 | | | | | | |
