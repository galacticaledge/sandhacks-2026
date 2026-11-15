# Bright Data credit log

Budget: **$100**. Ask a human before any single job estimated above **$15**.

| When (PT) | Job | Product | Requests / pages | Est. cost | Actual cost | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-14 14:40-15:35 | `collectors/web_reports.py`: news quotes about Tijuana River sewage odor / H2S ("What the web reported that night") | Web Unlocker, REST API (`POST api.brightdata.com/request`, zone `web_unlocker1`) | 94 sent, 93 succeeded (1 site-side 429, not billed) | $0.14 (93 x $1.50 per 1,000, the pay-as-you-go rate on brightdata.com/pricing/web-unlocker) | not readable: the token gets 403 on `/customer/balance`; check the dashboard | 15 probe requests while choosing the search method, then 6 windows: 2025-02-23..26, 2026-03-17..23, 2026-03-27..04-06, 2026-04-17..22, 2026-05-31..06-02 and the last 7 days. Fetched: KPBS monthly sitemaps, WordPress REST post listings (Times of San Diego, inewsource, Voice of San Diego, Coronado Times) and 45 article pages. 18 reports stored. |

## Web reports job (manual only)

Not in `api/scheduler.py` on purpose, so Bright Data spend stays under human control. Run by hand:

```
.venv/bin/python -m collectors.web_reports --since 7
.venv/bin/python -m collectors.web_reports --from 2026-04-17 --to 2026-04-22
```

- Every request is a Web Unlocker request. No SERP API: the account has no SERP zone and the token cannot create
  one (`POST /zone` returns 403). Search is each news site's own date-bounded listing, not Google.
- Running count of requests: `data/raw/web_reports/requests.jsonl` (one line per request sent). The CLI prints the
  total and the estimated cost after each run. The collector stops at 1,500 requests ($2.25).
- Cache: `data/raw/web_reports/pages/` plus `index.jsonl` (url, file, fetch time). A cached URL is not refetched;
  listings for a window that includes today are refetched after 6 hours. A rerun of a past window costs $0.
- A typical new window costs 10 to 15 requests (about $0.02). Add a row to the table above after each run.

- **San Diego County boundary** (`web/public/sd-county.geojson`): U.S. Census Bureau TIGERweb, State_County layer, GEOID 06073 (public domain), retrieved 2026-11-15. Used only to fade the map outside the county and draw the county line.
