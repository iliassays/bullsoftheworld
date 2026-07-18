# DSE native-edge program — production-server results

Status: completed read-only diagnostic; no strategy admitted

Run date: 18 July 2026

Server code: `f0e28fe`

Frozen specification: `bb7f1f2f712e16e70ac5ca74028f78acd32ff5954ce97522a0f1824b3330f376`

Window: 1 January 2025 through the latest completed DSE session, 16 July 2026

## Decision

The honest result is not an investable edge. The quality/value portfolio made money in absolute
terms, but did not beat an exposure-matched DSEX/cash benchmark. The existing reversal proxy and
all four newly preregistered DSE hypotheses lost money after the frozen execution assumptions.
Nothing in this batch may be promoted to a target, order, paper fill or Atlas shadow portfolio.

Quality/value remains a candidate for the long-only core because it preserved most of the market's
upside with a diversified, capacity-aware book. It is not yet evidence of alpha. Every tactical
hypothesis in this batch is rejected as written.

## Portfolio results

| Read | Portfolio | Comparable benchmark | Excess | Stress portfolio | Max drawdown | Completed trades | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| Quality/value core | +10.987% | +11.639% at matched 85% gross | -0.652% | +9.223% | 13.822% | 60 sells | Retain as core candidate; no alpha claim |
| Existing `deep_reclaim` proxy | -5.095% | +12.019% DSEX | -17.114% | -5.575% | 7.649% | 15 | Reject historical proxy |
| Earnings drift | -17.534% | +14.891% DSEX | -32.425% | -20.970% | 20.095% | 64 | Reject |
| Dividend revision | -5.662% | +7.014% DSEX | -12.677% | -6.716% | 6.964% | 12 | Reject; sample also insufficient |
| Insider buy declaration | -3.799% | +13.634% DSEX | -17.433% | -4.537% | 3.996% | 13 | Reject; sample also insufficient |
| Daily leader pullback | -13.174% | +12.979% DSEX | -26.153% | -16.977% | 13.861% | 45 | Reject |

The event-strategy benchmark interval begins at the first executable trade and ends at the last
completed exit, so its DSEX return is not the same number in every row. The quality/value comparison
uses an 85% DSEX / 15% cash baseline to match its target gross exposure.

## Train, validation and test read

Quality/value returned -2.804% in January–June 2025 against -5.831% for the exposure-matched
benchmark, -7.730% in July–December 2025 against -7.779%, and +12.285% in 2026 against +12.532%.
This is useful downside participation, but the test period's -0.247 percentage-point excess does
not support an alpha claim.

The four new hypotheses did not fail because of one bad split. Earnings drift had negative mean
excess in train, validation and test; its 71 completed observations had mean excess -4.828% and a
clustered 95% confidence interval of -6.368% to -3.351%. Daily leader pullback also had negative
mean excess in every split; its 48 observations had mean excess -4.052%. Insider declarations had
only five completed test observations and positive raw mean return, +0.778%, but still lagged DSEX
by 5.271 percentage points. Dividend revision had only 12 completed observations overall.

## Legacy Hedge reconciliation

The current production Hedge application contains two different performance claims:

- its daily-screen header hard-codes a previously validated `+73.6%` two-year return; and
- its persisted historical simulation currently reports `+84.844%` from 27 June 2024 through
  16 July 2026, versus `+10.176%` for DSEX, with 79 completed trades, 59.49% wins and -11.46%
  maximum drawdown.

The second number is dynamically computed, but neither number is comparable with this audit. The
legacy engine fills at the same session's close, uses fractional shares, has no slippage, capacity,
integer-share, settlement or sector constraints, selects alphabetically when signals compete for
cash, filters all historical securities using their latest 20-session liquidity, and approximates
fundamental availability from fiscal year rather than an actual publication timestamp. Its prices
and DSEX are also not adjusted total-return series. It is a useful exploratory result, not an
institutional track record.

The separate Hedge signal ledger has 250 signals since January 2025, of which 243 are resolved and
seven remain open. Its +11.399% average resolved signal result is not a portfolio return: consecutive
dates can create overlapping signals for the same company, and the ledger does not constrain them by
one shared capital account.

The production database has no DSE Atlas shadow portfolio. It also has no simulated-agent execution
for BXPHARMA, BRACBANK or SQURPHARMA in this window, and the current Hedge signal ledger has no row for
those three names in this window. Any previously displayed rows for those names were not executions
in the current production books and must not be used as proof of profitability.

## Evidence boundary

The run opened a read-only database transaction and used only a server temporary directory for the
runner. It created no production file, schema change, signal, target, order, fill or shadow book.
The server supplied 366 DSE sessions, 174,094 daily-bar rows for 359 currently active equities, and
11,979 announcements. The fixed quality input contained 233 current, active, non-Z equities marked
ready or partially research-ready.

This remains a diagnostic rather than a promotable backtest because the current universe creates
survivorship bias, prices lack corporate-action adjustment, DSEX is not a total-return benchmark,
and announcements lack an intraday receipt timestamp. Approximately eighteen months is also not a
complete market cycle. Ownership accumulation remains data-blocked by sparse snapshots and rating
changes by only two decoded actions; historical intraday trend-pullback remains data-blocked because
sampled intraday history does not exist.

## Next institutional move

Do not tune these losing rules against the same sample. First make performance truth consistent and
point-in-time: remove the hard-coded Hedge headline, label the legacy backtest's assumptions, build
corporate-action-adjusted security returns and a DSEX total-return comparator, preserve listing and
delisting history, and attach effective receipt timestamps to fundamentals and announcements.

After that foundation is testable, preregister a second DSE batch around economic mechanisms rather
than cosmetic parameter variants: quality/value conditioned on valuation and market regime;
earnings surprise conditioned on the pre-announcement move to distinguish drift from sell-the-news;
and liquidity/flow pressure with realistic capacity. Quality/value is the only current candidate
worth rebuilding with point-in-time data; it is not admitted to a forward shadow on these results.
Any future book must first pass its immutable admission report, then begin from zero on a declared
inception date rather than inherit a fabricated historical paper record.
