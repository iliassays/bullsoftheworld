# DSE edge validation — 2026-07-16

## Decision

No newly tested DSE edge is approved for a new paper-trading agent. The existing
`QualityReversalPortfolio` remains active only to collect genuine forward evidence from immutable
EOD decisions. It must not be backfilled from historical signals.

## Data boundary

- 193,990 DSE daily bars, 2024-06-23 through 2026-07-15
- 235 currently active, non-Z, equity instruments passed the executable-universe filter
- DSEX benchmark through 2026-07-14
- no adjusted DSE closes are populated
- current-symbol universe: inactive and delisted history is incomplete
- announcements: 4 records; block trades: one historical day; ownership: roughly three snapshots
  per stock

The event/news/ownership datasets are not deep enough for honest PEAD, block-flow, or ownership-flow
agents. The ownership study has 430 lagged observations but only `+0.018` rank IC; apparent group
returns mostly reflect the rising market.

## Protocol

- Signals use completed bars through T; entries fill at the next available session open.
- Brokerage is 0.40% per side; base slippage is 0.25% per side and stress slippage 0.75%.
- Trailing median value traded must be at least BDT 5 million.
- A BDT 1 million book may use at most 2% of trailing ADV and 10% NAV per position.
- DSE sell proceeds become reusable after T+2 settlement.
- Upper-limit locked next sessions are treated as unfillable.
- Stop is assumed to execute before target when both are touched in one daily bar.
- Trades without a complete horizon are excluded unless stop or target already resolved them.
- One-day close gaps above 35% are excluded as potential corporate-action contamination.
- Chronological windows: train before 2025-07-01; validation through 2025-12-31; test from
  2026-01-01.
- Promotion requires positive median net return, positive mean excess return, profit factor above
  1.10, minimum sample size, and survival under stressed slippage in every window.

Implementation:

- `packages/analytics/src/bulls/analytics/dse_edges.py`
- `packages/analytics/src/bulls/analytics/dse_edge_backtest.py`
- `scripts/dse_edge_lab.py`
- `packages/analytics/tests/test_dse_edges.py`

## Results

| Hypothesis | Full event read | 2026 test event read | 2026 test book vs DSEX | Decision |
|---|---:|---:|---:|---|
| Deep washout + 5-session reclaim | mean +5.69%, PF 2.13 | mean +1.00%, median -10.94%, excess -1.83% | +0.07% vs +17.80% | Reject; same family as existing forward account |
| Capitulation-volume + reclaim | 1 executable event | no test events | no book | Reject; insufficient |
| High-participation deep reclaim | mean +2.77%, median -8.96% | mean -2.84%, excess -5.52% | -2.32% vs +19.05% | Reject |
| Up-regime high-volume limit continuation | mean -0.73%, PF 0.81 | mean -0.51%, median -4.12% | -8.71% vs +17.40% | Reject |

The deep-reclaim neighbor sweep did not rescue the recent regime:

- strict: 9 test outcomes, mean +1.27%, median -10.94%
- base: 15 test outcomes, mean +1.00%, median -10.94%
- broad: 27 test outcomes, mean -0.51%, median -10.94%

The positive full-period deep-reclaim portfolio is therefore regime aggregation, not sufficient
evidence of a current edge.

## Interpretation

1. Volume is useful for predicting continued *attention*, but not trade direction. Requiring high
   trigger volume made the reversal worse in the recent test.
2. Near-limit positive moves do not survive realistic costs. They are useful alerts, not entries.
3. The washout/reclaim family remains economically plausible, but its payoff is right-skewed and
   unstable. A few targets hide a median stop-out in the 2026 test.
4. The correct action is forward collection, not another overlapping agent. The existing exact
   `QualityReversalPortfolio` already provides that experiment and currently has zero fabricated
   historical trades.

## Research context

- DSE return-volume research finds return shocks lead volume more reliably than volume leads
  returns, consistent with our rejection of directional volume agents:
  https://doi.org/10.7759/s44404-026-00103-2
- Historical DSE momentum is market-state dependent, but the present two-year sample and costed
  test reject the high-volume continuation implementation:
  https://doi.org/10.1142/S0219091517500114
- DSE panel construction must preserve each instrument's actual observation window; padding can
  materially suppress measured volatility:
  https://arxiv.org/abs/2603.20237

## Next evidence milestone

Re-run this fixed protocol monthly without changing thresholds. Reconsider promotion only after:

- at least 30 resolved forward `QualityReversalPortfolio` trades,
- at least 60 completed forward market sessions,
- positive excess return after fees and slippage,
- maximum drawdown no greater than 15%,
- stable results across both rising and falling DSEX regimes.
