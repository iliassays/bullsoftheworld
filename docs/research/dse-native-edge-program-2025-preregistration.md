# DSE native-edge program — fixed 2025–present comparison

Status: preregistered diagnostic; frozen before post-signal returns were inspected

Recorded: 18 July 2026

## Scope and evidence boundary

Every previous and new read uses DSE data on the production server and the same signal window:
**1 January 2025 through the latest completed DSE session**. The runner opens a read-only database
transaction and writes only its JSON report to standard output. It creates no signal row, target,
order, fill, shadow book or production file.

The historical split is fixed before results:

- train: 1 January through 30 June 2025;
- validation: 1 July through 31 December 2025;
- test: 1 January 2026 through the latest completed session.

The current server universe is used only because effective-dated DSE listing history is absent.
That creates survivor bias. Prices are unadjusted and dividend total return is unavailable. These
limitations block promotion regardless of an attractive diagnostic.

## Shared execution contract

- Signal information is accepted only after its completed date; earliest fill is the next available
  DSE session open.
- Assumed capital is BDT 10 million, target position weight 8.5%, maximum ten positions, and maximum
  participation is 2% of trailing 20-session median traded value.
- A signal is executable only when capacity supports at least half its intended position.
- Base costs are 0.40% fee and 0.25% slippage on each side. Stress slippage is 0.75% on each side.
- Integer shares, limit-locked entry rejection and T+2 sale-proceeds settlement apply.
- Results are compared with DSEX over the same invested interval. Event observations are clustered
  by signal date when estimating the excess-return confidence interval.
- A strategy cannot pass from mean return alone. It needs at least 30 completed observations,
  positive test excess, positive stressed portfolio excess, maximum drawdown no greater than 15%,
  and a positive lower clustered 95% confidence bound. Historical eligibility would still require
  a separate forward shadow decision.

## Previous reads

1. `deep_reclaim` is the registered historical proxy for the existing DSE liquid-reversal thesis:
   the existing immutable detector, 63-session maximum hold, 10% stop and 25% target.
2. `dse_quality_value_v1` uses the frozen conservative quality proxy, quarterly review, capacity-
   aware weights, maximum 10% per name, maximum 25% per sector and 85% target gross.
3. The actual `dse_reversal_v1` server shadow snapshots are reported only from their real inception;
   Atlas must not fabricate a January 2025 paper history for a book that did not exist then.

## New primary hypotheses

### `dse_earnings_drift_v1`

Slow investor processing may cause post-announcement drift after a material earnings improvement.
An event qualifies when the decoded DSE announcement contains comparable current and prior EPS,
current EPS is positive, and either the company moves from non-positive to positive EPS or EPS rises
at least 25% year on year. Duplicate company/date/period reports create one event. The primary trade
has a 20-session maximum hold, 10% stop and 25% target.

### `dse_dividend_revision_v1`

A material cash-distribution improvement may reveal management confidence and attract slower income
capital. A decoded cash-dividend declaration qualifies only when Atlas already has an earlier
declaration for that company. It must initiate at least a 5% cash dividend after a recorded zero, or
increase cash dividend by at least two percentage points and 20%. Disbursement notices without a
new rate do not qualify. The primary trade has a 20-session maximum hold, 8% stop and 20% target.

### `dse_insider_buy_declaration_v1`

A director or sponsor's public intention to buy may contain forward information before the purchase
is completed. A current-equity announcement qualifies when its headline identifies a buy
declaration. Later buy confirmations are excluded from signal creation. Multiple declarations for
one company on one date form one event. The primary trade has a 20-session maximum hold, 10% stop
and 25% target.

### `dse_leader_pullback_daily_v1`

Persistent relative leaders may resume after an orderly, low-volume pullback. Before the signal a
company must have at least 126 sessions, 126-session return of at least 20%, at least ten percentage
points of 126-session strength over DSEX, price above its 50-session mean, and the 50-session mean
above its 126-session mean. DSEX must be above its own 50-session mean. The preceding five sessions
must pull back 1–7% from their high on below-20-session-average volume. The signal session must close
above the preceding three-session high, at or above and no more than 5% over its 20-session EMA, with
volume at least equal to the pullback average. Signals have a 20-session cooldown, 40-session maximum
hold, 8% stop and 20% target. This is an EOD hypothesis, not a proxy backfill for the data-blocked
intraday trend-pullback book.

## Multiple-testing decision

These four new primary hypotheses are the complete July 2026 DSE batch. Variants and secondary
horizons are not selected after viewing results. A strong-looking train result cannot rescue a weak
test result, and the best of four is not promoted merely because it ranks first. Ownership
accumulation and rating-change tests remain data-blocked: ownership has only two to five snapshots
per company without historical receipt timestamps, and only two rating notices contain a decoded
upgrade/downgrade action.
