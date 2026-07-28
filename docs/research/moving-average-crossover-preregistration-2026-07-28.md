# Moving-average crossover preregistration

Registered: 28 July 2026

Experiment keys:

- `dse_bullish_ma20_50_v1`
- `us_bullish_ma20_50_v1`

Status: specification frozen before the experiment outcomes were inspected.

## Question

Does the first completed daily `SMA(20)` crossover above `SMA(50)`, when both averages are rising
inside an established long-term uptrend, identify executable continuation after costs?

The shared illustration is a trend-state description, not a complete strategy. A moving-average
crossover is delayed by construction and can repeatedly whipsaw in a range. This experiment tests
the transition event without treating the words "bullish crossover" as evidence of profitability.

## Economic mechanism

If information is incorporated gradually, the faster average can turn above the slower average
while slower investors are still repricing the security. Requiring both averages to rise and price
to remain above its long-term mean attempts to isolate broad participation from a mechanical
short-covering bounce. The extension guard prevents the experiment from buying an already
exhausted price jump.

The expected failure is that the averages confirm only after most of the move has occurred, or
that sideways markets create enough false transitions to consume the continuation premium.

## Frozen primary rule

All calculations use completed daily bars only.

- Fast average: 20-session simple moving average.
- Slow average: 50-session simple moving average.
- Regime average: 200-session simple moving average.
- Transition: today's `SMA(20) > SMA(50)` and yesterday's `SMA(20) <= SMA(50)`.
- Slope gate: both averages are above their values five completed sessions earlier.
- Regime gate: completed close is above `SMA(200)`.
- Price confirmation: completed close is above `SMA(20)`.
- Extension guard: completed close is no more than `1.5 * ATR(14)` above `SMA(20)`.
- Entry: next session open, never the crossover close.
- Exit decision: first completed close below `SMA(50)`.
- Exit fill: next session open.
- Maximum holding period: 63 completed sessions; the timeout decision also fills at the next open.
- One open position per security. A continuing bullish state cannot create another entry.

The five-session slope and `1.5 ATR` values are fixed before inspection. No volume, RSI, sector,
fundamental, cap-tier or catalyst condition is added after seeing results.

## Universe and execution

| Contract | DSE | US |
|---|---:|---:|
| Instruments | Active product-eligible equities outside category Z | Active product-eligible common stocks and ADRs |
| Minimum history | 200 completed sessions | 200 completed sessions |
| Minimum 20-session average turnover | BDT 5 million | USD 1 million |
| Minimum signal price | BDT 5 | USD 1 |
| Normal one-way cost | 65 bps | 30 bps |
| Stressed one-way cost | 100 bps | 60 bps |
| Independent benchmark | DSEX | SPY |

DSE uses raw OHLC and excludes an episode if a raw close-to-close move above 35% appears in the
60-session signal lookback or holding interval. US OHLC is put on the adjusted-close scale using
the same-session adjustment factor. Invalid or incomplete OHLC rows are quarantined, not repaired.

## Chronological windows

DSE:

- discovery: through 30 June 2025;
- validation: 1 July through 31 December 2025;
- holdout: 1 January 2026 onward.

US:

- discovery: through 31 December 2022;
- validation: 1 January 2023 through 31 December 2024;
- holdout: 1 January 2025 onward.

The US store contains current survivors rather than a point-in-time historical universe. DSE
prices are not fully corporate-action adjusted. Positive results are therefore upper bounds; a
negative result is sufficient to reject this implementation.

## Required reports

For every market and chronological window:

- completed trades, independent signal dates and securities;
- mean and median net return, win rate, profit factor and holding duration;
- mean benchmark-relative return;
- signal-date cohort mean with a 63-session circular block-bootstrap interval;
- maximum favorable and adverse excursion;
- normal and stressed cost results;
- result after removing the two largest winners;
- entry gaps and data-quarantine counts.

## Admission gates

This diagnostic creates no Agent Decision, target, paper order, squeeze state or public Idea. A
separate Trend Continuation monitor may be proposed only if validation and holdout both have:

1. at least 30 completed trades and 20 independent signal dates;
2. positive median net and benchmark-relative return;
3. positive stressed-cost cohort return;
4. a block-bootstrap 95% benchmark-relative confidence-interval floor above zero;
5. profit factor above 1.10;
6. positive mean net after removing the two largest winners.

Passing these gates would permit a capacity- and concurrency-constrained portfolio diagnostic,
not production promotion. Failing them means the crossover may remain a descriptive chart fact
but must not be labeled an opportunity or buy signal.
