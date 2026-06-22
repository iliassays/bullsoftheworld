---
name: scrape-check
description: Validate the DSE scraper still pulls clean data. Run after dsebd.org changes or before relying on data.
---

# /scrape-check — validate DSE data ingestion

The project's #1 risk is data. Run this whenever dsebd.org might have changed.

1. Pull the instrument list via `DseScrapeProvider.list_symbols()` — sanity-check the count
   (DSE has ~350+ instruments; a sudden drop means the parser broke).
2. Pull quotes for a few liquid codes (`GP`, `BEXIMCO`, `SQURPHARMA`) and assert fields are
   populated and numeric, and `is_delayed=True` with a sane `as_of`.
3. Pull a short daily-bar range for one code and check OHLC ordering (low <= open/close <= high).
4. Report: counts, sample rows, and any field that came back empty/None.

If parsing fails, the dsebd.org page layout likely changed — fix the selectors in
`packages/market_data/.../providers/dse_scrape.py`.
