# US Security Master

The US universe must be onboarded through a security master before any ticker reaches retail UX.
US listings include common stocks, ETFs, ADRs, preferred shares, warrants, rights, units, notes,
test issues, and deficient issuers. Treating the raw listing file as the product universe would
pollute search, SEO, screeners, alerts, and RAG.

## Layers

1. Raw security master: `security_master`
   - One row per listed instrument we know about.
   - Keeps source provenance, raw symbol, normalized symbol, exchange, instrument type, ETF flag,
     test flag, financial status, CIK, and eligibility.
   - Inactive or excluded rows remain auditable.

2. Product symbol universe: `symbols`
   - Retail-facing and tenant-facing.
   - Receives only rows where `is_product_eligible=true`.
   - For the first US pass this means active common stocks, ADRs, and ETFs; warrants, rights,
     units, preferreds, debt-like instruments, test issues, and deficient Nasdaq issuers are hidden.

3. Market data and fundamentals
   - Price bars, quote snapshots, SEC filings, XBRL facts, analytics, RAG chunks, and SEO are built
     after identity is stable.
   - Ticker changes and multiple share classes should be handled in the security-master layer, not
     scattered across product features.

## Sources

- Nasdaq Trader `nasdaqlisted.txt`: Nasdaq-listed securities.
- Nasdaq Trader `otherlisted.txt`: NYSE, NYSE Arca, NYSE American, Cboe BZX, IEX, and other listed
  securities.
- SEC `company_tickers_exchange.json`: CIK enrichment for filing and XBRL joins.

## Guardrail

Do not write product features that branch on `if market == "US"` to interpret instruments. Add
capabilities, provider adapters, or market/security-master metadata instead.
