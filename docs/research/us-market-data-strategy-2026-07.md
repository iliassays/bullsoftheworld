# US market-data strategy (research memo, 2026-07-16)

Status: recommendation agreed with the owner on 2026-07-16. The options Phase A ingestion
foundation has started; price-provider migration and vendor acquisition remain outstanding.
Audience: the next engineering session that picks up the provider migration. Read
`docs/architecture/institutional-research-os.md` (data readiness + licensing sections) first.

## Where the US tenant's data actually comes from today

Yahoo Finance's **unofficial** endpoints (spark batch + v8 chart) currently feed:

- universe discovery price/liquidity observations (`bulls.market_data.providers.us_universe_discovery`);
- 10-year onboarding backfills (`ingestion.history` via `us_yahoo`);
- the daily US EOD bars that are publicly displayed on bullsofwallst.com for the
  ~367 `ready` symbols and consumed by Atlas (queue, dossier, Hypothesis Lab).

DSE is unaffected (own scraper against dsebd.org).

## Why this must change (in order of urgency)

1. **No contract.** Yahoo's API is reverse-engineered; auth (crumb/cookie) and rate limits have
   tightened repeatedly. The entire US data plane can break without notice.
2. **ToS exposure.** Yahoo's published API terms restrict commercial derivation and redistribution.
   A free or small product is not an exemption. Yahoo-derived bars must not be treated as an
   authorized customer-facing source without explicit permission.
3. **Structural inadequacy for research.** No delisted symbols, no point-in-time, silent
   corporate-action revisions — the exact reasons US Hypothesis Lab backtests are permanently
   stuck at `diagnostic`.

## Agreed target: three-tier data plane, migrated by tier

| Tier | Source | Status / action |
|---|---|---|
| Temporary discovery bootstrap | Yahoo (unofficial) | Remove from customer-facing and production fallback paths. Any continued private cross-check requires terms review; no new dependency is allowed. |
| Production EOD (internal Atlas reads) | **Tiingo** — tiingo.com | Migrate first only under a plan licensed to the actual subscriber. The low-cost individual plan is not a business-product license; the internal commercial plan is for internal use and does not grant public redistribution. |
| Customer-facing EOD display | **Licensed redistribution/display agreement** | Obtain explicit display and redistribution rights from Tiingo or another vendor before public or paid US display. Fail closed rather than falling back to Yahoo. |
| Research-grade history (point-in-time, delisted-inclusive, 1998+) | **Sharadar Core US Equities** — data.nasdaq.com/databases/SFA | Evaluate this quarter. The only tier Yahoo structurally cannot serve; unlocks `validated` US backtests. Quote via Nasdaq Data Link. |
| Options research — underlying-level | **Cboe DataShop "Option Sentiment"** — `datashop.cboe.com/Documents/Cboe_OptionSentiment_Specs.pdf` | Historical feasibility source. Buy ~1yr first; subscribe only after the registered stock-selection test shows incremental value. One EOD file for all optionable underlyings, including iv30/iv90, normalized 25d skew, net option delta, directional premium, implied borrow, size/DTE/moneyness buckets, and baselines. |
| Options research — chain display | **Cboe Option EOD Summary or licensed OPRA-derived vendor** | Required for the actual contract chain: point-in-time bid/ask, volume, previous-settlement open interest, IV, Greeks, and liquidity flags. Quote and customer-display/retention rights pending. Do not pretend the underlying-level sentiment file is a full chain. |
| Options research — exact flow labels | **Cboe Open-Close Volume Summary** | Evaluate after the feasibility stage. Supplies participant, buy/sell, and open/close classification on Cboe exchanges; partial-market coverage must remain visible. External derived display requires additional licensing/approval. |

**Hard rule:** nothing new gets built on Yahoo. Catalysts run on EDGAR, forensics on
EDGAR/FINRA, options on Cboe. Every added Yahoo dependency is migration debt.

The options research contract is
`docs/research/us-options-flow-research-2026-07.md`. Its hard rules include:

- options flow is an evidence lens, not a recommendation;
- directional delta and volatility demand are separate;
- open interest is previous-settlement state and cannot prove same-day opening;
- exact Open-Close labels outrank inferred OPRA bid/ask classification;
- the first registered strategy trades the underlying stock, not options;
- blank fields mean unavailable, not zero;
- no customer-facing chain or derived alert ships until the exact license permits it.

## Implementation plan (next session picks up here)

1. **Watchdog (free, immediate):** probe US EOD bar freshness/schema against the expected session
   so a Yahoo breaking change pages instead of rotting silently. `ingestion.sec_watchdog` and the
   post-EOD freshness checks in `ingestion.watchdog` are the pattern; verify what the existing US
   checks already cover before adding.
2. **Tiingo provider (first real step):** new adapter in `packages/market_data/providers/`
   implementing the existing `MarketDataProvider` interface; registry flip for authorized internal
   US EOD. Customer-facing reads fail closed unless the configured authorization explicitly permits
   display/redistribution. Yahoo is not an automatic public fallback. Config via env (e.g.
   `TIINGO_API_KEY` on `bulls.core.config.Settings`) — **never hardcode a key, never commit one**.
   The account/key must belong to this business (see licensing note below).
3. **Backfill reconciliation:** before flipping, reconcile Tiingo vs stored Yahoo bars on the 367
   ready symbols (close/adjusted-close/volume tolerances; flag corporate-action disagreements).
   Store the reconciliation report; omit-over-mislead applies to discrepancies.
4. **Sharadar evaluation:** score against Hypothesis Lab's own gates (survivorship, delistings,
   corporate actions, point-in-time fundamentals, history length). Success = the
   inactive/delisted-universe gate can pass for US.
5. **Options schema audit:** obtain Option Sentiment history plus Option EOD Summary and Open-Close
   samples. Reconcile symbol identity, sessions, blank fields, exchange coverage, previous-settlement
   open interest, adjusted contracts, and delivery times before adding a serving model. The
   entitlement gate, immutable manifests, strict Option Sentiment v1.4 parser, normalized Parquet
   writer, quality report, and manual bounded import are implemented; no licensed data is loaded.
6. **One licensing review, three source families:** Tiingo commercial terms + Sharadar quote + Cboe/
   OPRA internal, display, derived-data, retention, and redistribution terms, decided together as
   one memo. This also closes the open licensing item from
   `docs/research/platform-intelligence-research-2026-07.md`.

## Separate second-product boundary

The proposed cross-venue arbitrage/dislocation scanner is not an Atlas module. Its discovery memo
is `docs/research/cross-venue-dislocation-product-2026-07.md`. It may reuse provenance, identity,
calculation, replay, alerts, and audit concepts, but not Atlas research scores, licenses, or
validation labels.

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
