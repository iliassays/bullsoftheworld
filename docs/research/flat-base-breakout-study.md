# High-volume flat-base breakout study

Date: 12 July 2026

## Question

Can a strict flat base identify DSE stocks before an ITC-like expansion, and does the structure
have enough historical edge to be presented as a trading signal?

## Point-in-time rule

The production candidate requires:

- a liquid stock with at least Tk 5 million average daily turnover;
- a rising 50-session average and an as-of close above that average;
- a 15-session range no deeper than 10%, with at least two resistance touches;
- base volume that has not expanded above 1.2x its earlier base volume;
- `forming`: close within 5% below resistance;
- `confirmed`: close at least 0.5% above resistance, no more than 8% extended, at least 2x base
  volume, and in the upper 35% of the session range.

Every feature uses only bars available on the signal date. The event study enters at the next
session open, charges 0.4% on entry and exit, applies a 20-session signal cooldown, and measures a
20-session horizon.

## Data and split

- 418 DSE symbols, 192,406 daily bars
- 23 June 2024 through 9 July 2026
- training signals before 1 July 2025, with outcomes also ending before the split
- untouched validation signals on or after 1 July 2025

This is a short, current-symbol data set. The split prevents direct look-ahead but does not remove
survivorship bias or establish performance across a full market cycle.

## Results

| Sample | Events | Median 20d | Positive 20d | Touched +10% | +15% | +20% | Median MFE / MAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| Strict flat base, train | 20 | -5.70% | 30.0% | 20.0% | 5.0% | 5.0% | +3.8% / -8.5% |
| Generic 20d volume breakout, train | 301 | -7.23% | 22.6% | 25.6% | 12.6% | 7.0% | +4.5% / -11.9% |
| Strict flat base, validation | 67 | +1.11% | 53.7% | 43.3% | 22.4% | 14.9% | +8.3% / -6.3% |
| Generic 20d volume breakout, validation | 688 | -1.32% | 45.3% | 39.4% | 26.5% | 17.4% | +7.7% / -7.5% |

The existing portfolio-level generic volume-breakout control also produced only +2.3% total return,
34% winning trades and -27.8% maximum drawdown under its standard stop/target assumptions.

## ITC replay

Using only contemporaneous data, the strict detector reports:

- 22 June 2026: `forming`, resistance Tk 43.9;
- 23 June 2026: `forming`, resistance Tk 43.9;
- 24 June 2026: `confirmed_breakout_up`, close Tk 44.8, 3.35x base volume, 7.6% base depth.

This demonstrates that the rule recognizes the motivating example without using later bars.

## Decision

Ship it as a **framework-level research watchlist**, not as a backtested buy signal.

The strict filter improved typical validation returns and downside versus the generic control, but
the training period remained negative and large-outcome hit rates were not consistently superior.
The portal may say a stock is `forming` or has `moved above` the base and show the exact resistance,
depth and volume confirmation. It must not show an explosion probability, expected return, buy
label or `backtested` evidence chip.

Re-evaluate after at least five years of split-adjusted history, delisted-symbol coverage, several
market regimes, and live forward alerts with executable slippage.

Reproduce with:

```bash
uv run python scripts/flat_base_breakout_study.py
```
