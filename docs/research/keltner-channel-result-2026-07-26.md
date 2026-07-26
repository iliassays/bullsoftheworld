# Keltner channel momentum result

Evaluated: 26 July 2026

Preregistration: `keltner-channel-preregistration-2026-07-26.md`

Experiment keys:

- `dse_keltner_momentum_v1`
- `us_keltner_momentum_v1`

Decision: **rejected as a standalone entry strategy in both markets**.

## What was tested

The frozen primary rule used an `EMA(20) +/- 2 * Wilder ATR(20)` channel. A first completed close
outside the channel formed the signal, entry occurred at the next session open, and an opposite
close through the EMA exited at the following open. Results include market-specific two-sided
costs, turnover and price floors, a 63-session maximum hold, independent DSEX/SPY comparisons and
chronological discovery, validation and holdout windows.

The scanner was read-only. It created no Atlas Agent Decision, target, paper order or UI state.

## Primary results

| Market/direction | Window | Trades | Mean net | Median net | Cohort excess | 95% excess CI | Profit factor |
|---|---|---:|---:|---:|---:|---:|---:|
| DSE long | Validation | 324 | +1.13% | -3.41% | -0.32% | [-2.74%, +2.15%] | 1.26 |
| DSE long | Holdout | 374 | -0.37% | -4.11% | -1.71% | [-4.08%, +0.59%] | 0.92 |
| US long | Validation | 23,076 | -0.23% | -2.63% | -1.78% | [-2.47%, -1.15%] | 0.95 |
| US long | Holdout | 19,096 | -0.65% | -3.30% | -1.82% | [-3.48%, -0.53%] | 0.89 |
| US short diagnostic | Validation | 17,190 | -2.06% | -3.48% | +0.92% | [+0.21%, +1.68%] | 0.60 |
| US short diagnostic | Holdout | 14,309 | -2.68% | -4.06% | -0.72% | [-2.61%, +0.93%] | 0.58 |

The US short validation excess was positive only because the market benchmark fell in the short
direction; the strategy itself lost 2.06% per trade after costs and then lost absolutely and
relatively in holdout. It is not evidence for a short book.

Both registered robustness neighbors, `ATR(10), 2.0x` and `ATR(20), 2.5x`, failed the stressed
validation/holdout sign checks. The primary rule failed the median, stressed cohort, confidence
floor, benchmark-relative and holdout profit-factor gates. It is not eligible for a portfolio
diagnostic.

## Data-quality finding

The first US run stopped on invalid OHLC input, as required. Production inspection found 1,219
invalid-range rows across the broader US daily-bar store, concentrated in 17 and 24 July 2026.
Among the experiment's eligible common-stock/ADR universe, the audited adapter quarantined 3,034
rows across 355 securities:

- 353 invalid OHLC-range rows;
- 2,681 rows without an adjusted close.

No value was repaired or imputed. Invalid rows were excluded and the omissions were recorded in
the result artifact. The experiment remains negatively decisive despite the store's
current-survivor bias, but the latest-session OHLC issue must be fixed in ingestion before
certifying any future US model.

## Interpretation

The shared illustration describes a trend-following indicator, not an economic edge. An upper-band
close can identify expansion, but indiscriminately buying every cross enters many late,
mean-reverting and crowded moves. The losing medians and sub-one holdout profit factors show that a
small number of winners cannot pay for the broad population after executable costs.

Keltner position may remain a descriptive feature for volatility-normalized trend state. It must
not be displayed as a validated buy/sell rule or copied into Agent Decisions.

A distinct successor may test a preregistered mechanism such as prior compression plus abnormal
participation, accumulation persistence, market/sector regime and extension control. That would be
a new hypothesis and experiment key. These validation and holdout results may not be reused to
select its thresholds.

