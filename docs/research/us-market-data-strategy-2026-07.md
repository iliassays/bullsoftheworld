# US market-data strategy (research memo, 2026-07-16)

Status: recommendation agreed with the owner on 2026-07-16; implementation not started.
Audience: the next engineering session that picks up the provider migration. Read
`docs/architecture/institutional-research-os.md` (data readiness + licensing sections) first.

## Where the US tenant's data actually comes from today

Yahoo Finance's **unofficial** endpoints (spark batch + v8 chart) currently feed:

- universe discovery price/liquidity observations (`bulls.market_data.providers.us_universe_discovery`);
- 10-year onboarding backfills (`ingestion.history` via `us_yahoo`);
- the daily US EOD bars that are publicly displayed on bullsofwallst.com for the
  ~367 `ready` symbols and consumed by Atlas (queue, dossier, Hypothesis Lab).

DSE is unaffected (own scraper against dsebd.org). bullstreetai (separate private project)
also uses Yahoo — that is fine and out of scope: internal-only pipeline, no display, no customers.

## Why this must change (in order of urgency)

1. **No contract.** Yahoo's API is reverse-engineered; auth (crumb/cookie) and rate limits have
   tightened repeatedly. The entire US data plane can break without notice.
2. **ToS exposure.** Yahoo prohibits commercial redistribution. Public display of Yahoo-derived
   bars is defensible only while the product is free and small; it is indefensible for paid Atlas.
   The architecture doc's own words: "Yahoo remains a bootstrap discovery source, not commercial
   authority."
3. **Structural inadequacy for research.** No delisted symbols, no point-in-time, silent
   corporate-action revisions — the exact reasons US Hypothesis Lab backtests are permanently
   stuck at `diagnostic`.

## Agreed target: three-tier data plane, migrated by tier

| Tier | Source | Status / action |
|---|---|---|
| Discovery + cross-check | Yahoo (free, unofficial) | Keep. Internal breadth scanning only. |
| Production EOD (public display + Atlas reads) | **Tiingo** — tiingo.com | Migrate first. ~$30/mo Power plan for internal use now; commercial/redistribution addendum via sales@tiingo.com before paid launch. |
| Research-grade history (point-in-time, delisted-inclusive, 1998+) | **Sharadar Core US Equities** — data.nasdaq.com/databases/SFA | Evaluate this quarter. The only tier Yahoo structurally cannot serve; unlocks `validated` US backtests. Quote via Nasdaq Data Link. |
| Options (catalyst-scoped) | **Cboe DataShop "Option Sentiment"** — datashop.cboe.com/option-sentiment | Decided 2026-07-16, quote pending. Buy ~1yr historical first, subscribe after validation. Ask explicitly for display/external-use license pricing, not just internal use. Spec: one EOD file for all optionable underlyings (~80 fields incl. iv30/iv90, norm 25d skew, net option delta, directional premium, implied_borrow, size/DTE/moneyness buckets, 20d baselines). Blank fields mean "no data" → must render as unavailable/illiquid, never zero. |

**Hard rule:** nothing new gets built on Yahoo. Catalysts run on EDGAR, forensics on
EDGAR/FINRA, options on Cboe. Every added Yahoo dependency is migration debt.

## Implementation plan (next session picks up here)

1. **Watchdog (free, immediate):** probe US EOD bar freshness/schema against the expected session
   so a Yahoo breaking change pages instead of rotting silently. `ingestion.sec_watchdog` and the
   post-EOD freshness checks in `ingestion.watchdog` are the pattern; verify what the existing US
   checks already cover before adding.
2. **Tiingo provider (first real step):** new adapter in `packages/market_data/providers/`
   implementing the existing `MarketDataProvider` interface; registry flip for US EOD; Yahoo
   demoted to automatic fallback + cross-check. Config via env (e.g. `TIINGO_API_KEY` on
   `bulls.core.config.Settings`) — **never hardcode a key, never commit one**. The account/key
   must belong to this business (see licensing note below).
3. **Backfill reconciliation:** before flipping, reconcile Tiingo vs stored Yahoo bars on the 367
   ready symbols (close/adjusted-close/volume tolerances; flag corporate-action disagreements).
   Store the reconciliation report; omit-over-mislead applies to discrepancies.
4. **Sharadar evaluation:** score against Hypothesis Lab's own gates (survivorship, delistings,
   corporate actions, point-in-time fundamentals, history length). Success = the
   inactive/delisted-universe gate can pass for US.
5. **One licensing review, three vendors:** Tiingo commercial terms + Sharadar quote + Cboe
   display license, decided together as one memo. This also closes the open licensing item from
   `docs/research/platform-intelligence-research-2026-07.md`.

Related but separate: DSE history extension candidate is the Mendeley DSE EOD dataset
(doi 10.17632/23553sm4tn.4, CC BY 4.0, Oct 2012–Jan 2026, raw + adjusted + instrument-availability
metadata). Reconcile against our scraped 2024-06→present bars before trusting; counsel review
before it feeds any paid surface.

## Licensing ground rules for API keys (agreed 2026-07-16)

- Market-data subscriptions are licensed to a **named subscriber entity** and are non-transferable.
  A key issued to another company (e.g. a former employer) must not be used in this product: the
  vendor can revoke it without notice, usage is attributable to the wrong entity, and it creates
  exactly the redistribution liability this migration exists to remove.
- Every production key lives in `.env` on the server / deployment secrets, is owned by the Bulls
  business (or Ilias personally during the free phase), and its plan tier must actually permit the
  usage (internal vs display).
