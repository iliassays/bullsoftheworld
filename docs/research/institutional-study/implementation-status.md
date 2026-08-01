# Systems A/B/C — Atlas Implementation Status

**Implementation baseline:** Atlas portfolio engine v2.  
**Scope:** US private research workspace only. DSE strategy behavior and data remain isolated.

This file is the operator contract between the institutional study and the application. A system
being visible in Atlas does not mean it is validated, deployable, or connected to live capital.

## Shared controls now implemented

- Immutable strategy identity, methodology version, trial sequence, specification hash, and failed
  experiment retention.
- Completed-information signal clock with institutional fills no earlier than the next observable
  session close.
- Adjusted economic price histories, per-name point-in-time spread estimates, explicit fees,
  ADV participation limits, settled-cash limits, position/sector/gross caps, and 10/30/50 bps
  one-way cost stress.
- Two-rung drawdown ladder. The flatten rung is sticky in historical and shadow books; no
  counterfactual review is invented to re-arm a historical run.
- Chronological train/validation/test reporting, deflated Sharpe against the registered family
  trial count (counted across ALL workspaces in the tenant/market, so a fresh workspace cannot
  reset the multiple-testing penalty), named-regime reporting, persisted evidence fingerprints,
  and objective shadow promotion gates.
- The 30 bps kill rule is a first-class gate: an edge that dies at or below 30 bps one-way fails
  the run to diagnostic (phase 13 §13.2), independent of the null-model comparisons.
- Event books are additionally gated against the uncosted market benchmark at realistic and
  30 bps costs (phase 12 market null); the 21-session placebo answers timing, not exposure.
- Event books also run a 1/N null (`equal_weight_all_events`) through the same harness: equal
  weight in **every** candidate event, unscreened and unranked, entering on the same session the
  book's signal maps to and ageing out on the same time stop. The universe is deliberately the
  candidates *before* screening — equal-weighting the screened set would be a near-copy of the
  book, a null that cannot lose. The book must therefore show that its screen and its sizing
  earn their complexity, not merely that events carry a return.
- The DSE books carry the same market null (`equal_weight_eligible_universe`): 1/N across every
  security whose trailing 20-session traded value clears the strategy's own liquidity floor,
  recomputed from completed sessions at each of the strategy's rebalance dates. They previously
  had a timing placebo and a liquidity-only baseline but never had to beat simply holding the
  market, so a DSE book could have passed while its name selection contributed nothing.
- Code-resident constants that define an event family (activist roster fragments, book policy,
  cluster parameters, placebo delay) are embedded in the frozen specification hash — editing one
  produces a new specification, never a silent rewrite of a frozen trial's history.
  - **One-time consequence, by design:** trials registered before this change, and every A2 trial
    registered while the cluster minimum was one insider, cannot reproduce their own
    `specification_hash` under the current code. They are not corrupt and they are not deleted —
    they are historical records of a *different* specification, and the new hash correctly refuses
    to claim continuity with them. Any comparison across that boundary must be stated as a
    comparison of two specifications, never as one strategy's track record.
- Known deviation, disclosed: the shared engine applies the risk policy's 10% per-position stop
  to event books. Phase 12's System A exit spec (thesis-break / time-stop / staged) does not
  include it. The stop is part of the hashed risk policy, so a no-stop variant can be registered
  as its own trial and decided by evidence.
- Forward shadow books persist intended versus constrained orders, fills, risk interventions,
  targets, fees, turnover, decision prices, implementation shortfall, and explicit
  freeze-clearance events.
- US market predicates are hard-coded in the institutional data adapters. Workspace, portfolio,
  run, and decision records remain tenant-and-market bound by API checks and database row-level
  security.

## System A1 — activist 13D event book

**Implemented:** EDGAR acceptance-time event reconstruction, curated activist rule, separate
strategy identity, point-in-time spread and shares data, equal-weight event book, position/book
caps, staged time exits, immediate thesis-break exits, next-close execution, cost tiers, rejected
candidate reasons, and a 21-session delayed-entry placebo.

**Still blocks validation:**

- Complete inactive/acquired target history has not passed an audit.
- The crowding screen runs on FINRA short interest as a percent of shares outstanding
  (conservative for a long book); the preregistered percent-of-float input is still absent.
- Required named regimes must exist in the requested historical window.

## System A2 — opportunistic insider cluster book

**Implemented:** Form 4 code-P purchases, 10b5-1 exclusion, insider classification using only
filings accepted by that timestamp, cluster construction (minimum two distinct insiders per the
studied evidence — singleton purchases are excluded from the event family), separate strategy
identity, the same event-book execution/risk controls as A1, and the delayed-entry placebo.

**Cost of requiring a real cluster** (production query, 2026-08-01, non-10b5-1 code-P purchases
2016-2026, monthly issuer buckets as a proxy for the 30-day window): 30,781 issuer-windows have
at least one buying insider; 12,502 have two or more. Requiring a genuine cluster therefore
discards about 59% of events and retains 12,502 — a large reduction, but the remaining sample is
still ample for event-family evidence, so the sleeve is narrowed rather than starved. The
monthly bucket is an approximation of the rolling window and the true retained count will differ
somewhat.

**Still blocks validation:** the same listing-history, crowding-data, and regime-coverage gates as
A1. A user-selected ticker subset is diagnostic and cannot establish event-family evidence.

## System B — forced-seller/post-spin book

**Status: registered and data-blocked by design.**

Atlas refuses to simulate this system until all seven replayable datasets exist: authoritative
corporate-action history, announcement/effective timestamps, parent-holder history,
post-bankruptcy distributions, point-in-time fundamentals, inactive listings, and
corporate-action-safe prices. News text and current listings are not accepted as proxies. The UI
shows the missing datasets and prevents a shadow book from being created. The refusal is an
explicit admission rule in shadow creation (a data-blocked run with no simulated sessions is
rejected by name), not an incidental property of the empty result.

## System C — factor sleeve

**Implemented:** pre-start liquidity selection, append-only SEC fact observations, as-known
restatement handling, quarterly-to-TTM derivation, value/momentum/quality/low-issuance composite,
monthly buffered selection, portfolio constraints, next-close execution, and three same-harness
nulls: eligible-universe 1/N, naive momentum, and cap-weighted eligible universe.

**Still blocks validation:**

- The interactive universe is capped for runtime; promotion requires the uncapped historical
  universe including inactive listings.
- Historical capitalization-tier membership is not reconstructed. Current cap metadata cannot be
  projected backward.
- The requested history must cover the named stress regimes.

## Reading an Atlas result

1. **Registered** means the hypothesis and frozen specification are in the trial ledger.
2. **Prepared** means the available data can produce a diagnostic.
3. **Evidence gaps** means the simulation ran, but one or more named gates failed.
4. **Data blocked** means Atlas refused to approximate missing critical data.
5. **Shadow eligible** means every historical gate passed. It is not approval for live capital.
6. **Eligible after forward shadow** means the objective forward gates passed. A separate capital
   decision is still required; Atlas has no broker or live-order path.

## Verification commands

```bash
UV_CACHE_DIR=.uv-cache uv run ruff check packages/analytics/src services/api/src/api/institutional_research
UV_CACHE_DIR=.uv-cache uv run pytest packages/analytics/tests -q
UV_CACHE_DIR=.uv-cache uv run pytest services/api/tests/test_institutional_backtests.py -q
cd apps/research && npm run test && npm run build
```
