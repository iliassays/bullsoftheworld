# Keltner channel momentum preregistration

Registered: 26 July 2026

Experiment keys:

- `dse_keltner_momentum_v1`
- `us_keltner_momentum_v1`

Status: specification frozen before production outcomes were inspected.

## Question

Does a first daily close outside a volatility-normalized Keltner channel identify a persistent
trend that remains profitable after next-observable execution, market-specific costs, liquidity
limits and an independent benchmark?

The chart shared by the owner is an illustration, not a complete strategy. It does not name the
EMA period, ATR period, channel multiplier, fill convention, costs, capacity, repeated-signal
behavior or portfolio limits. This preregistration supplies those missing decisions before reading
an outcome.

## Primary rule

- Price basis: split/distribution-adjusted OHLC for US; raw DSE OHLC with corporate-action
  contamination filters.
- Middle line: 20-session EMA of completed closes, seeded by the first 20-session simple mean.
- ATR: 20-session Wilder average true range.
- Upper/lower channels: EMA plus/minus `2.0 * ATR`.
- Long signal: the first completed close above the upper channel after the prior close was not
  above its prior upper channel.
- Short signal: the first completed close below the lower channel after the prior close was not
  below its prior lower channel.
- Entry: next session open, never the signal close.
- Long exit: first completed close below the middle EMA, filled at the following session open.
- Short exit: first completed close above the middle EMA, filled at the following session open.
- Maximum holding period: 63 completed sessions; a timeout decision at a close fills at the next
  session open.
- One open position per security. A continuing close outside the channel does not create another
  entry.
- DSE is long-only. US short outcomes are diagnostic only and cannot create a paper strategy
  without point-in-time locate, borrow availability, borrow fee, recall and buy-in evidence.

## Universe and execution

| Contract | DSE | US |
|---|---:|---:|
| Instruments | Active product-eligible equities | Current common stocks and ADRs |
| Minimum 20-session average turnover | BDT 5 million | USD 1 million |
| Minimum signal price | BDT 5 | USD 1 |
| Normal one-way cost | 65 bps | 30 bps |
| Stressed one-way cost | 100 bps | 60 bps |
| Independent benchmark | DSEX | SPY |
| Maximum concurrent names for later portfolio admission | 3 | 10 |

Costs are applied through adverse entry/exit slippage and fees. A result also reports zero-cost
gross return so cost sensitivity is visible. DSE rows with a close-to-close move beyond 35% in the
20-session signal lookback or holding window are excluded as potential corporate-action
contamination. US rows with invalid or missing adjusted prices are excluded.

## Chronological windows

DSE:

- discovery: through 30 June 2025;
- validation: 1 July through 31 December 2025;
- holdout: 1 January 2026 onward.

US:

- discovery: 1 January 2018 through 31 December 2022;
- validation: 1 January 2023 through 31 December 2024;
- holdout: 1 January 2025 onward.

The current US store is a survivor universe and DSE history is short and unadjusted. A positive
result is therefore an upper bound and cannot establish an institution-grade edge. A negative
result is sufficient to reject this implementation.

## Required reports

For each market, direction and chronological window:

- completed trades, independent signal dates and securities;
- mean and median net return, win rate, profit factor and holding duration;
- mean and median benchmark-relative return;
- signal-date cohort mean with a holding-length block-bootstrap interval;
- maximum favorable/adverse excursion;
- normal and stressed cost results;
- dependence on the two largest winners;
- the percentage of entries that gap materially beyond the signal close.

The primary rule is not selected from alternatives. Two neighboring definitions are reported only
as sign-stability checks and cannot replace the primary result:

- `EMA(20), ATR(10), 2.0x`;
- `EMA(20), ATR(20), 2.5x`.

## Admission gates

This experiment creates no Agent Decision or paper target. A successor may be proposed only if the
primary rule has all of the following in validation and holdout:

1. at least 30 completed trades and 20 independent signal dates;
2. positive median net and benchmark-relative return;
3. positive stressed-cost cohort return;
4. a block-bootstrap 95% confidence-interval floor above zero;
5. profit factor above 1.10;
6. positive result after removing the two largest winners;
7. no sign reversal in either neighboring-definition check;
8. a separately run concurrency- and capacity-constrained portfolio that beats DSEX/SPY.

Passing those quantitative gates would start a distinct, registered portfolio diagnostic. It
would not repair missing delisted history, DSE adjustments or US borrow data and would not by
itself authorize a forward book.
