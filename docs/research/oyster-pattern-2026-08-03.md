# Oyster pattern: daily approximation research

Recorded: 3 August 2026

Experiment keys:

- `dse_oyster_daily_v1`
- `us_oyster_daily_v1`

Code:

- `packages/analytics/src/bulls/analytics/oyster.py`
- `research/edge_discovery/oyster.py`
- `scripts/oyster_pattern_research.py`

## Source hypothesis

The user supplied **Oyster Pattern shared again Oct 5**, a 37-slide deck prepared by Michael
Franks in June 2025. The deck uses selected two-hour and four-hour low-priced US charts. Its core
description is:

1. price crosses a manually drawn falling resistance line;
2. price drifts along the right side of that line for several bars;
3. the author accumulates during a claimed 15%-30% drift;
4. a large move is expected within roughly 4-12 days.

The deck contains useful positive and negative chart examples. It does **not** provide a formal
denominator, point-in-time universe, complete failures, delisted names, corporate-action policy,
liquidity/capacity constraints, executable entry and exit rules, costs, controls, or an untouched
holdout. Its 50%-100% gain and high-success-rate claims are therefore anecdotal and must not be
shown as Atlas evidence. The name also does not appear to be a discoverable standard technical
analysis taxonomy. Atlas treats it as a private hypothesis, not an established pattern.

## Frozen daily approximation

Atlas does not have complete historical two-hour/four-hour bars for both DSE and US. Version
`oyster-daily-v1` therefore tests a daily approximation and states that mismatch in every research
artifact.

The rule uses completed bars only:

1. Fit the latest three to six confirmed swing highs within 120 sessions.
2. Require falling resistance to decline at least 10%, with fit residual no more than 1.25 ATR.
3. Require a material prior decline of at least 30%.
4. Require a completed close to cross resistance by 0.15 ATR; the crossing session may not rise
   more than 25% (15% for the DSE study).
5. Observe at least two and at most twelve later sessions.
6. Require the retest to remain above the extrapolated falling line within 0.75 ATR, draw down no
   more than 30%, extend no more than 25% before activation, and trade no more than 1.2 times its
   prior 20-session average volume.
7. Optional activation requires a later close above the post-cross range by 0.10 ATR on at least
   1.5 times baseline volume.
8. Archive only the first eligible state in a 30-session episode.

Study eligibility is market-policy driven:

| Market | Analysis start | Price | 20-session average turnover | Additional quarantine |
|---|---:|---:|---:|---|
| DSE | 2024-06-01 | at least BDT 5 | at least BDT 5m | any unadjusted 120-session close jump above 35% |
| US | 2023-01-01 | $0.25-$10 | at least $1m | adjusted OHLC required |

## Outcomes

The first observable retest state is an **attention event**, not an order. The event study records:

- close-to-close returns after 1, 3, 5, 10 and 20 completed sessions;
- maximum future high and minimum future low over each horizon;
- 20-session +10% and +20% opportunity rates;
- market-benchmark excess returns;
- liquidity, strength, retest drawdown and volume contraction;
- discovery, validation and holdout periods separately.

Current listed/product-eligible securities create survivorship bias, so any positive result is an
upper bound. Promotion requires a separate matched-control test, stable validation and holdout
lift, executable entry/exit rules, costs, capacity, and survivorship-complete evidence. Until that
gate passes, this work may support an experimental chart-research board only; it must not create
an Agent Decision, target, paper position, notification, or “move coming soon” claim.

## Relationship to prior work

The hypothesis overlaps but is not identical to `us_former_runner_reactivation_v1`. That study
required an extreme recent runner, deep pullback, and retained abnormal volume. It reconstructed
STAK but failed matched controls overall and was rejected. Oyster v1 instead tests the falling-line
break and controlled retest explicitly. A positive chart anecdote cannot override the former-runner
rejection, and duplicated episodes across the two studies are not independent trials.

## Decision

Pending production DSE and US event studies. Market conclusions remain separate.
