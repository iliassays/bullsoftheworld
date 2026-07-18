# DSE quality-universe lab — July 2026

Status: corrected diagnostic; quality-value remains a candidate, not admitted or rejected

This read-only production audit corrects the broad-universe factor experiment. It did not write a
signal, target, order, shadow-book position, or database row. The existing Atlas
`dse_reversal_v1` book remains unchanged.

## Production data-lineage audit

The server already contains the DSE daily and company history used here; it does **not** need a
full redownload. The read-only audit found 192,776 daily bars for 401 symbols and 487 DSEX sessions
from 27 June 2024 through 16 July 2026, plus annual and dividend records for most listed companies.
Those rows are useful, but their historical knowledge boundary is incomplete:

- all 192,776 daily-bar observations were bootstrapped with one `known_at` date rather than the date
  on which Atlas originally received each bar;
- annual, dividend, profile and shareholding observations also share the bootstrap knowledge date;
- adjusted closes are absent;
- DSE security-listing observations contain zero rows, so current membership cannot be projected
  backward without survivorship bias.

The working tree now adds a failure-isolated, forward-only DSE listing writer. On each accepted
instrument snapshot it records added, updated and removed identities in the existing lineage
tables. Duplicate, cross-market, implausibly small and sharply truncated snapshots fail closed
before they can deactivate securities. This starts honest history from deployment onward; it does
not invent past listing dates, replace the existing daily history, or change the blocked intraday
strategy. It is local and undeployed.

## The investment question

An exchange feed is inventory, not a portfolio. Atlas must transform raw coverage in this order:

1. valid equity and identity;
2. sufficient observation and data integrity;
3. absolute company-quality evidence known at that historical time;
4. minimum tradability;
5. strategy-specific rank;
6. portfolio capacity, concentration, cash, settlement, and execution constraints.

Company quality and order capacity are deliberately separate. A good smaller company can remain in
the research universe while the constraint engine sizes it down or rejects the order. It must not
be relabelled as a low-quality company merely because an 8.5% target is too large.

## Frozen quality proxy

The production source has annual EPS, NAV and dividend history, but not full historical cash-flow,
balance-sheet, margin, accrual, or filing-publication facts. The current gate is therefore an
honest *quality proxy*, not a complete institutional quality model:

- current active, non-hidden, research-ready/partial, non-Z DSE equity;
- at least 126 daily observations and a bar on the immediately following DSE session;
- no suspicious recent close gap greater than 35%;
- trailing median traded value of at least BDT 5 million;
- three consecutive profitable conservatively known fiscal years;
- positive NAV, ROE at least 10%, P/E no greater than 25, and P/B no greater than 4;
- latest EPS at least 50% of the prior two-year average;
- a cash dividend in at least two of those three fiscal years.

Because annual-report publication timestamps are absent, only fiscal years no later than signal
year minus two are treated as known. Full BDT 850,000 position capacity at 2% of trailing traded
value is reported separately. The assumed account is BDT 10 million.

## Universe audit

The input security master contained 233 current active, non-Z equities. The quarterly point-in-time
proxy reduced that pool before ranking:

| Review date | Observable | Quality + tradability | Full-size capable | Targets |
|---|---:|---:|---:|---:|
| 2025-01-08 | 231 | 24 | 2 | 10 |
| 2025-04-16 | 232 | 21 | 3 | 10 |
| 2025-07-24 | 232 | 34 | 8 | 10 |
| 2025-10-26 | 232 | 38 | 3 | 10 |
| 2026-01-26 | 233 | 30 | 5 | 10 |
| 2026-05-07 | 232 | 37 | 11 | 10 |

Across 1,392 security-date observations, the most common exclusions were low ROE (730),
insufficient BDT 5 million liquidity (564), excessive P/E (340), inconsistent profitability (291),
and EPS collapse (192). A company can fail more than one gate.

This is the corrected answer to the owner's concern: the strategy never sees all 233 names as
equivalent opportunities. It sees only 21–38 quality/tradability-qualified names at a review.

## Experiment 1: reversal inside quality only

The registered deep-reclaim detector produced 86 raw price signals. Only 13 occurred inside the
quality universe, and only one could execute under the BDT 10 million capacity policy. That one
training observation returned +23.69% net, but validation and test contained zero executable
observations.

Decision: **data-insufficient; do not call this working or failing.** One trade is not a backtest.
It does prove that the quality gate removes nearly all broad washout noise. The existing Atlas
reversal shadow book must remain unchanged rather than being silently converted into this variant.

## Experiment 2: quarterly quality at a reasonable price

The corrected portfolio ranks value only inside the passing quality universe, selects ten names,
targets 85% gross, reviews quarterly, and changes targets at the next open. It has no arbitrary
swing stop or profit target. The simulation includes 0.40% fees, 0.25% slippage, integer shares,
2% trailing-value participation, and T+2 sale-proceeds settlement. Dividend income is excluded
because ex-dividend and payment dates are unavailable.

| Window | Portfolio | 85% DSEX + cash | Excess | Full DSEX | Max DD | Avg gross |
|---|---:|---:|---:|---:|---:|---:|
| Full | +9.16% | +11.64% | -2.48% | +13.59% | 8.89% | 49.4% |
| Train | +2.46% | -5.83% | +8.29% | -6.85% | 4.54% | 42.1% |
| Validation | -2.06% | -7.78% | +5.72% | -9.14% | 6.89% | 43.1% |
| Test | +4.24% | +12.53% | -8.29% | +14.78% | 8.09% | 57.2% |

At stressed 0.75% slippage, the full result was +7.99%, 3.65 percentage points below the
85%-DSEX/cash benchmark, with 9.04% maximum drawdown.

These numbers are informative but not admissible. Forty-one target changes were capacity-limited,
so the book averaged only 49.4% gross rather than its intended 85%. It behaved defensively during
the falling train/validation markets and lagged sharply in the rising test market. The target list
was also heavily bank-concentrated, showing that cross-sector P/E, P/B and ROE ranking is not yet a
finished institutional portfolio model.

Decision: **keep `dse_quality_value_v1` as a candidate; create no shadow book yet.** The corrected
test neither proves an edge nor justifies rejecting the economic hypothesis.

## Experiment 3: capacity- and sector-aware quality portfolio

The next diagnostic changes portfolio construction, not the quality thesis. It ranks the same
qualified universe, permits up to 20 names, caps one name at 10%, caps one sector at 25%, and sizes
each target no larger than one session of permitted trailing-value participation. Buy cash is
allocated as one pro-rata batch, so a ticker's alphabetical or score iteration order cannot consume
cash before its peers.

| Window | Portfolio | 85% DSEX + cash | Excess | Full DSEX | Max DD | Avg gross |
|---|---:|---:|---:|---:|---:|---:|
| Full | +10.99% | +11.64% | -0.65% | +13.59% | 13.82% | 75.9% |
| Train | -2.80% | -5.83% | +3.03% | -6.85% | 8.05% | 75.6% |
| Validation | -7.73% | -7.78% | +0.05% | -9.14% | 14.75% | 82.9% |
| Test | +12.29% | +12.53% | -0.25% | +14.78% | 9.96% | 79.9% |

At stressed 0.75% slippage, the full result was +9.22%, 2.42 percentage points below the
85%-DSEX/cash benchmark, with 13.98% maximum drawdown. Average gross exposure rose from 49.4% to
75.9%, and capacity shortfalls fell from 41 to 14. Feasible target gross by review was 79.39%,
72.66%, 85.00%, 85.00%, 84.63%, and 84.62%; target counts were 20, 20, 19, 20, 20, and 16.

Decision: **adopt the allocator as the better DSE research constructor, not as evidence of alpha.**
It made the intended portfolio more feasible and diversified, but the full, stressed and untouched
test results did not beat the mandate-matched benchmark. The larger drawdown is the honest cost of
removing the old strategy's accidental cash cushion.

## DSE fund-level research boundary

Atlas now has a deterministic, non-executing DSE sleeve aggregator for the future fund architecture.
Each strategy supplies its own target weights, evidence state, priority and maximum sleeve budget.
One fund-level risk authority then applies shared name, sector, gross and minimum-cash constraints
and records every reduction. Its output is only a diagnostic target with
`capital_action = none`: it cannot create an order, fill, paper position, performance series or
new shadow book.

This keeps `dse_reversal_v1` and `dse_quality_value_v1` independent while making their potential
overlap visible. They should not be blended into a reported fund result until each sleeve has an
immutable specification and admissible evidence. The data-blocked intraday trend-pullback remains
outside this allocator until its own readiness gates pass.

## What Atlas adds—and what is still missing

Atlas is valuable when it makes these distinctions durable and replayable:

- raw coverage versus point-in-time research universe;
- qualified company versus strategy signal;
- desired target versus constrained order versus actual fill;
- company quality versus liquidity/capacity;
- absolute return versus mandate-matched benchmark and risk;
- valid evidence versus missing evidence and honest abstention.

The next quality release should not add more indicators. It should add the missing institutional
facts and controls:

1. DSE annual-report `known_at` timestamps and immutable historical revisions;
2. operating cash flow, free cash flow, leverage, interest coverage, margins, accrual quality and
   sector-specific quality rules, especially separate bank/insurer treatment;
3. adjusted prices, corporate-action lineage, and total-return benchmark/dividend events;
4. effective-dated DSE security identity and inactive/delisted history;
5. a longer historical panel spanning several bull, bear, liquidity and policy regimes.

Until those exist, Atlas should show the 21–38-name quality research universe and its rejection
reasons, but must not market a quality-value track record or claim that the candidate is validated.

## Reproduction

```bash
uv run python scripts/dse_quality_universe_lab.py
uv run pytest -q packages/analytics/tests/test_dse_quality_universe.py \
  packages/analytics/tests/test_dse_quality_portfolio.py \
  packages/analytics/tests/test_dse_fund_allocator.py
```
