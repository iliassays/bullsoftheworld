# Spec: Symbol page realignment (tabbed)

**Status:** Building (P-A) · **Date:** 2026-06-26

We've accumulated more structured data than a single scroll can hold (price/TA, valuation, ownership,
earnings/dividends, buzz, agent notes). Reorganise the symbol page into tabs (StockTwits-style), with
our differentiators — the **🐂 Bulls** notes feed and **Ownership** flow — as first-class tabs.

## Layout
A persistent **header** (always visible) + a **tab bar**.

- **Header:** ticker, name, price, today's change, after-close, `👁 N watching (+M wk)`, Watch toggle,
  "Attention rising" chip, and a **fundamentals quick-strip** (Mkt Cap · Vol · 52W H/L · P/E · EPS).
- **Tabs:** Overview · 💬 Feed · 🐂 Bulls · Fundamentals · Ownership · Earnings _(News = Phase 3)_.

| Tab | Contents | Source |
|---|---|---|
| **Overview** | "What's happening" digest, chart, key levels, technicals | existing endpoints |
| **💬 Feed** | user discussion, composer, agree/disagree, replies, most-discussed | `/posts` |
| **🐂 Bulls** | agent desk-notes for this ticker (never lost under chatter) | `/posts?kind=note` |
| **Fundamentals** | Mkt Cap, P/E, P/B, yield, EPS, NAV, shares, free float, face value, sector P/E, credit rating | **new** `/company` |
| **Ownership** | sponsor / foreign / institutional / public split + month-over-month deltas, as-of date | **new** `/company` |
| **Earnings** | historical EPS / NAV / profit + dividend history (no forward estimates — we don't fabricate) | **new** `/company` |

## New endpoint: `GET /symbols/{code}/company`
One call powers the three data tabs:
```jsonc
{
  "fundamentals": { "market_cap_mn", "pe_ratio", "pb_ratio", "dividend_yield", "pe_vs_sector",
                    "eps", "nav_per_share", "eps_growth_yoy", "outstanding_shares",
                    "free_float_cap_mn", "face_value", "sector", "credit_rating" },
  "ownership": { "sponsor_pct", "institute_pct", "foreign_pct", "public_pct",
                 "institute_delta", "foreign_delta", "as_of" },   // null fields when unknown
  "earnings": [ { "fiscal_year", "eps", "nav_per_share", "profit_mn" } ],
  "dividends": [ { "year", "cash_pct", "bonus_pct" } ]
}
```
Sources: persisted `TickerAnalytics` (valuation + ownership %s/deltas) + `CompanyProfile` (eps, nav,
shares, rating, …) + `AnnualFinancial` + `DividendRecord`. Read-only. Omit-over-mislead: any field
we can't compute is `null` and the UI shows "—", never a guess.

## Principle
Descriptive only, delayed/as-of stamped, Bangla-first. No forward estimates or fabricated values.

## Phases
- **P-A (now):** the `/company` endpoint + the tabbed re-layout (Overview/Feed/Bulls/Fundamentals/
  Ownership/Earnings) + fundamentals quick-strip.
- **P-B:** Pulse gauges (crowd lean / message volume / participation) + a descriptive "why it's
  moving" explainer.
- **P-C:** the news parser → News tab (+ the dividend/earnings agents).
