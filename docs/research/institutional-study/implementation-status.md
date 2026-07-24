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
  trial count, named-regime reporting, persisted evidence fingerprints, and objective shadow
  promotion gates.
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
- Short interest as a percentage of float is absent; daily short volume is not substituted.
- Required named regimes must exist in the requested historical window.

## System A2 — opportunistic insider cluster book

**Implemented:** Form 4 code-P purchases, 10b5-1 exclusion, insider classification using only
filings accepted by that timestamp, cluster construction, separate strategy identity, the same
event-book execution/risk controls as A1, and the delayed-entry placebo.

**Still blocks validation:** the same listing-history, crowding-data, and regime-coverage gates as
A1. A user-selected ticker subset is diagnostic and cannot establish event-family evidence.

## System B — forced-seller/post-spin book

**Status: registered and data-blocked by design.**

Atlas refuses to simulate this system until all seven replayable datasets exist: authoritative
corporate-action history, announcement/effective timestamps, parent-holder history,
post-bankruptcy distributions, point-in-time fundamentals, inactive listings, and
corporate-action-safe prices. News text and current listings are not accepted as proxies. The UI
shows the missing datasets and prevents a shadow book from being created.

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
