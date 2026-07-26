# US former-runner reactivation experiment

Recorded: 26 July 2026

Experiment key: `us_former_runner_reactivation_v1`

Code:

- `research/edge_discovery/former_runner.py`
- `research/edge_discovery/test_former_runner.py`
- `scripts/us_former_runner_research.py`

## Decision

**Reject the fixed EOD watch rule as a general edge. Do not schedule it, create an Agent Decision,
or open a paper book.**

The rule reconstructed STAK correctly on 23 July, before its 24 July expansion. That is a useful
case validation, but the same fixed sequence did not beat matched controls across history.
Selecting one spectacular winner and explaining it after the event is not evidence that the
explanation predicts the next winner.

## Frozen sequence

The hypothesis was not "buy high volume." It required:

1. a prior session within 10 sessions whose close rose at least 40%, high rose at least 50%, and
   volume exceeded five times its prior 20-session average;
2. a 40%-75% pullback from the runner high;
3. a final session that did not lose more than 5%;
4. two quiet sessions, each moving no more than 12% and each retaining at least three times the
   pre-runner volume baseline;
5. a $0.50-$5.00 watch price and at least $500,000 watch-session turnover.

The outcome was deliberately an **opportunity**, not P&L: did the maximum high during the next
three sessions exceed the watch session's high by at least 20%? A secondary threshold measured
50%.

Five tests cover the STAK sequence, repeated-volume requirement, prefix causality, control
construction, and outcomes whose barrier is known before the three-session window completes.

## STAK reconstruction

Atlas stored the required sequence:

| Observation | Stored result |
|---|---:|
| Runner date | 2026-07-16 |
| Watch date | 2026-07-23 |
| Runner close return | +68.08% |
| Runner volume / prior 20-session average | 167.53x |
| Pullback from runner high | -70.00% |
| First quiet probe / pre-runner volume | 4.67x |
| Second quiet probe / pre-runner volume | 3.38x |
| Watch close / high reference | $1.32 / $1.43 |
| Next stored maximum high | $12.00 |
| Expansion above the $1.43 reference | +739.16% |

The three-session outcome window is still open, but both the +20% and +50% opportunity barriers
have already been reached. This does not reconstruct an executable trade: the daily bar cannot
tell whether the $1.17 low happened before or after a $1.43 stop-entry trigger.

## Historical result

The production study covered 5,888 current common-stock and ADR symbols from 2023 onward. Controls
were matched by date, trailing-dollar-volume band, and trailing-volatility band.

| Window | Completed | +20% opportunities | Matched control | Lift | Median max expansion |
|---|---:|---:|---:|---:|---:|
| Discovery 2023-2024 | 35 | 20.00% | 16.73% | +3.86pp | +1.51% |
| Validation 2025 | 35 | 14.29% | 11.51% | +2.78pp | -1.64% |
| Retrospective 2026 | 17 | **0.00%** | 14.92% | **-14.92pp** | +1.65% |
| All completed | 87 | 13.79% | 14.25% | **-0.29pp** | +0.60% |

Only one of 87 completed episodes reached the +50% threshold. Average maximum expansion was
+5.06%, substantially above the median because a few outliers dominate the distribution.

STAK is not included among completed events, so excluding it does not change these figures.
`SLND` also formed the watch state on 24 July, but has no observed future session yet. It is an
unresolved research observation, not a recommendation.

## Data and inference limits

- The rule was derived after inspecting STAK; there is no untouched 2026 holdout.
- US price history contains current survivors only, so positive results would be an upper bound.
- Atlas has zero US intraday bars.
- Atlas has point-in-time shares outstanding but no verified US free float.
- Atlas lacks historical borrow availability and cost-to-borrow.
- Atlas lacks independent external social-mention velocity.
- SEC filings provide dilution-risk flags, not a fully parsed warrant/ATM overhang.

The proposed live ignition rule needs one-minute volume, time-adjusted relative volume, session
VWAP, spread, and event ordering. Daily candles cannot substitute for those inputs.

## Conclusion

Repeated post-runner volume was genuinely present before STAK's move, but the fixed pattern is not
rare or predictive enough across the stored universe. The result agrees with Atlas's broader
finding that high relative volume becomes useful only when a separately validated mechanism and
entry policy make it selective.

Do not weaken thresholds after seeing these results. A successor is justified only after US
intraday collection exists and must receive a new experiment key and trial count. Until then STAK
is a valuable case study, not an algorithm.
