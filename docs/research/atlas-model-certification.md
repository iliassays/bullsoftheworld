# Atlas model certification

Status date: 2026-07-24

## Decision

Atlas is split into three independently gated layers:

1. **Portfolio engine**: deterministic accounting and execution controls.
2. **Research data foundation**: point-in-time, survivorship, identity, adjustment, and benchmark
   evidence.
3. **Strategy evidence**: economic hypothesis, null models, costs, regimes, and forward results.

A pass at one layer does not imply a pass at another. In particular, an engine certification does
not demonstrate investment alpha.

## Current status

| Layer | Status | Reason |
|---|---|---|
| Portfolio engine known-answer controls | PASS | Exact timing, NAV, fee/spread accounting, sell-before-buy funding, independent benchmark, and fail-closed benchmark tests pass |
| US research data foundation | NOT CERTIFIED | Production evidence has not yet attested complete inactive/delisted history, historical membership, corporate-action adjustments, and stable security identifiers |
| DSE research data foundation | NOT CERTIFIED | The same evidence-backed attestations are required; current DSEX coverage alone is insufficient |
| Published US momentum reproduction | BLOCKED | Requires historical market equity, NYSE/AMEX/NASDAQ membership, inactive securities, and comparison with the official return series |
| Systems A, B, and C alpha | NOT PROVEN | Existing trials remain diagnostic; prior market-relative figures must be rerun through engine v3 |

No strategy may become eligible for a shadow book because this document exists. Promotion continues
to require all historical, null, cost, regime, and forward gates in the investment mandate.

## Production audit snapshot

The existing read-only `data-foundation-v3` audit was run on 2026-07-24. It is an operational
foundation report, not the stricter certification introduced here.

### US

- 16,485,582 projected daily bars from 2016-07-11 through 2026-07-23.
- Daily-bar observation lineage ratio: 100%.
- Latest-session coverage among ready symbols: 97.37%.
- 8,428 active product symbols are research-ready, 2,529 partial, and 109 unavailable.
- One critical issue: analytics end at 2026-07-20 while bars end at 2026-07-23.
- 4,217,149 point-in-time SEC fact observations and 13,059 listing observations exist.
- Historical universe event history begins at the first guarded refresh; it does not prove a
  complete inactive/delisted membership history for the full backtest window.

Result: **not certified**. Refresh analytics, disposition onboarding failures, and produce the
historical identity/membership/adjustment attestations before rerunning strategy evidence.

### DSE

- 194,756 projected daily bars from 2024-06-27 through 2026-07-23.
- 396 of 396 ready symbols have the latest completed session.
- Daily-bar observation lineage ratio: 100%.
- No critical operational issue; one symbol has an unclassified capitalization tier.
- Fundamental `known_at` remains a conservative ingestion upper bound where source publication
  time is absent.

Result: **operationally current but not institutionally certified**. Two years of price history is
insufficient for broad regime claims, and the point-in-time fundamental timestamp limitation must
remain explicit.

## Material defects corrected

### 1. Implicit baseline presented as a benchmark

Engine v2 compounded a daily equal-weight return across the currently supplied security histories.
That series was exposed as `benchmark`, despite carrying current-universe, membership, and microcap
weighting bias.

Engine v3 separates:

- an explicit independent market series (`SPY` adjusted close for US; DSEX close for DSE);
- same-universe strategy nulls, run as portfolios through the same execution engine; and
- the observable-universe equal-weight diagnostic, which can no longer support promotion.

An explicit benchmark must cover at least 98% of evaluation sessions and include both boundaries.

### 2. Alphabetical order controlled settled-cash availability

Engine v2 processed rebalance orders by ticker. A buy in an alphabetically earlier ticker could be
cash-clipped before a later ticker sale released funds. Engine v3 deterministically executes
reductions before increases.

### 3. Warm-up history leaked into the evaluation window

The interactive institutional adapter used pre-start history correctly to form signals, but also
sent it into the execution window. Strategy NAV could remain in cash while the baseline moved
before the requested trial began. Signal construction still receives warm-up history; engine input
is now trimmed to the requested start and end dates.

### 4. Factor universe admitted non-equity instruments

The System C liquidity query read directly from daily bars. It now joins the security master and
restricts the research universe to common stocks and ADRs. ETFs, warrants, preferreds, rights, and
units cannot enter the equity factor sleeve.

## Deterministic controls

Run:

```bash
.venv/bin/python scripts/certify_atlas_engine.py
```

The command exits non-zero if any critical control fails. Tests cover:

- target decided at T fills no earlier than T+1;
- exact cash and NAV for a known zero-cost position;
- independent benchmark compounding;
- exact half-spread and fee arithmetic;
- sell-before-buy funding; and
- rejection of an implicit current-universe baseline for promotion.

## Data-foundation gate

`certify_data_foundation` produces a machine-readable pass/fail report. Structural checks inspect
duplicate series, duplicate bar keys, OHLC integrity, and explicit benchmark coverage. Evidence
attestations fail closed unless a dated audit artifact supports:

- inactive, acquired, and delisted histories;
- historical universe eligibility;
- point-in-time fundamentals and revisions;
- split and distribution adjustments; and
- stable identities across ticker changes and symbol reuse.

Boolean flags supplied by strategy code are not evidence. The evidence reference must resolve to a
dataset manifest or audit report.

## Published-factor control

The reproduction harness implements the official daily US momentum identity:

```text
Mom = 1/2 (Small High + Big High) - 1/2 (Small Low + Big Low)
```

It uses NYSE breakpoints, the six size-by-prior-return portfolios, lagged market-equity weights,
and a complete 251-session formation path. The methodology follows the
[Kenneth French Data Library daily momentum specification](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor_daily.html).
The broader [Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)
notes that the production portfolios include eligible NYSE, AMEX, and NASDAQ firms and that
historical values can change after source-data revisions.

Local reproduction requires at least 252 overlapping sessions, correlation of at least 0.80, and
an absolute mean daily-return gap no greater than 5 basis points against the official decimal
return series. These are engineering acceptance thresholds, not evidence that momentum will remain
profitable.

## Required reruns

After the production data foundation produces a valid attestation:

1. Run the published momentum reproduction and preserve its report.
2. Rerun Systems A and C with engine v3 and an explicit SPY series.
3. Keep System B blocked until its preregistered datasets exist.
4. Invalidate any stored market-relative verdict generated by engine v2.
5. Start or preserve shadow books only when historical promotion gates pass independently.
