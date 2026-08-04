# US segmented rank challenger preregistration

Recorded: 4 August 2026, before inspecting any challenger holdout result.

Status: **diagnostic only; cannot create an Atlas target, paper position, or order**.

## Question

Does separating the U.S. long-only rank model by observable tradability, abstaining outside a
supportive market regime, and applying capacity-aware inverse-volatility construction improve the
frozen v1 all-universe equal-weight diagnostic after costs?

This is a new hypothesis. The failed v1 artifact remains the comparison and is never overwritten.

## Data and temporal contract

- Current active, product-eligible U.S. common stocks and ADRs only.
- Completed daily bars and adjusted closes; features at session `t`, entry at open `t+1`.
- SPY-relative net returns over 5 and 20 non-overlapping sessions.
- Discovery exits no later than 31 December 2022.
- Validation signals begin after discovery and exits end no later than 31 December 2024.
- Holdout signals begin after validation and are inspected once.
- Normal round-trip cost comes from the frozen trailing-ADV cost schedule; stress doubles it.
- Survivor-only history blocks promotion regardless of performance.

## Causal regime

At the completed signal close:

- `risk_on`: SPY close is above its 200-session average and its 50-session average is above its
  200-session average;
- `risk_off`: both relations are reversed;
- `transition`: neither complete state applies;
- `high volatility`: trailing 20-session annualized SPY volatility is at least 25%; otherwise it is
  `normal`.

No future bar enters the regime label.

## Frozen sleeves

| Sleeve | Signal-close price | Trailing 20-session ADV | Allowed regime | Research book |
|---|---:|---:|---|---:|
| Deep liquidity | at least $5 | at least $50m | risk-on or transition; normal volatility | $5m |
| Institutional liquidity | at least $3 | $10m to below $50m | risk-on; normal volatility | $1m |
| Size-sensitive liquidity | at least $2 | $5m to below $10m | risk-on; normal volatility | $250k |

Each date also requires at least 50, 50, or 30 eligible names respectively. Sleeves do not overlap.
These are liquidity sleeves, not capitalization claims.

Historical cap-tier tests are **blocked**. Bulls does not possess point-in-time market cap across
the test history, and today's cap cannot be backfilled into old dates. Cap sleeves become a new
preregistered experiment only after dated capitalization is certified.

## Model and trial accounting

- Same 16 causal percentile features as the frozen linear baseline.
- One independently fitted ridge model per sleeve and horizon.
- Dimensionless ridge grid: `0.001, 0.01, 0.1, 1, 10`.
- Penalty selected on validation rank IC, with stressed return only as a tiebreaker.
- Fifteen registered penalty trials per horizon; thirty total for two horizons.
- No sleeve is selected, deleted, or relabelled using holdout performance.
- Naive 60-session residual momentum is evaluated through the same construction.

## Construction and abstention

- A candidate must have predicted net excess return above zero.
- At most 10 positions and at least 8 positions per rebalance.
- Inverse trailing-20-session-volatility weights.
- Maximum 15% per position.
- Maximum position notional equal to 1% of trailing ADV.
- If positive candidates or aggregate capacity cannot fund a diversified book, Atlas abstains for
  that rebalance date and records the reason.

## Decision rule

A sleeve is no better than diagnostic unless its untouched holdout has all of:

1. positive median daily rank IC;
2. positive mean return with doubled costs;
3. annualized Sharpe lower 95% confidence bound above zero;
4. at least 30 invested holdout rebalance dates.

Even a statistical pass remains promotion-blocked until point-in-time listing/delisting,
capitalization, identity, and corporate-action history is certified and 120 unchanged forward
sessions complete. A failed result is retained as evidence and cannot be repaired by changing the
thresholds against the same holdout.
