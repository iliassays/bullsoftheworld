# Moving-average crossover result

Evaluated: 28 July 2026

Preregistration: `moving-average-crossover-preregistration-2026-07-28.md`

Experiment keys:

- `dse_bullish_ma20_50_v1`
- `us_bullish_ma20_50_v1`

Decision: **rejected as an entry strategy in both markets**.

## What was tested

The frozen rule required the first completed `SMA(20)` crossover above `SMA(50)`, both averages
rising over five sessions, close above `SMA(20)` and `SMA(200)`, and extension no greater than
`1.5 * ATR(14)`. Entry occurred at the next session open. The first completed close below
`SMA(50)` caused an exit at the following open, with a 63-session maximum hold.

Results include market-specific two-sided costs, turnover and price floors, independent DSEX/SPY
comparisons, chronological discovery/validation/holdout windows, data quarantine and next-open
execution. The scanner was read-only and created no Atlas strategy, Agent Decision, target, paper
order or UI state.

## Primary results

| Market | Window | Trades | Mean net | Median net | Cohort excess | 95% excess CI | Profit factor |
|---|---|---:|---:|---:|---:|---:|---:|
| DSE | Validation | 15 | +1.84% | -1.73% | -2.34% | insufficient sample | 1.59 |
| DSE | Holdout | 24 | +0.69% | -3.24% | -3.30% | insufficient sample | 1.19 |
| US | Validation | 1,581 | -0.37% | -2.76% | -1.44% | [-1.98%, -0.86%] | 0.90 |
| US | Holdout | 1,334 | -0.31% | -3.19% | -0.92% | [-2.59%, +0.82%] | 0.93 |

DSE failed the sample, median, benchmark-relative, stressed-cost and outlier-dependence gates.
Its positive arithmetic mean came from a small winner tail: after removing the two largest
winners, mean net was -1.14% in validation and -1.50% in holdout. The holdout signal-date cohort
lost 0.88% net and 1.57% at stressed costs.

US failed every performance gate in both validation and holdout. Validation benchmark-relative
performance was significantly negative. Holdout mean net after removing the two largest winners
was -0.84%, win rate was 21.96%, and profit factor was 0.93.

## Data quality

DSE scanned 233 active, ready, non-category-Z product equities and quarantined no rows. Its raw
price basis and short history still prevent a positive institutional claim.

US scanned the active product universe and quarantined 3,121 rows across 106 securities:

- 104 invalid OHLC-range rows;
- 3,017 rows without an adjusted close.

No value was repaired or imputed. The current-survivor universe biases long results upward, so the
negative US result is not rescued by acquiring delisted history.

## Interpretation

The crossover is a lagging trend-state transition, not a profitable entry rule. On average the
fast and slow averages confirmed after enough of the move had occurred that subsequent whipsaws
and exits below the slow average consumed the remaining continuation.

The `SMA(20)`/`SMA(50)` relationship may remain a neutral chart or ticker-level trend fact. It
must not be shown as a validated bullish opportunity, added to public Ideas, mixed into the
squeeze taxonomy, promoted to Agent Decisions, or paper traded.

A future successor would need a distinct causal mechanism and preregistration. It may not tune
volume, pullback, cap-tier, RSI or catalyst filters against these validation/holdout outcomes and
reuse the same experiment key.
