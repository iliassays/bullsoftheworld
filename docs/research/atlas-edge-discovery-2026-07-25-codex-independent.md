# Atlas independent edge-discovery run - 2026-07-25

Status: independent diagnostic, not an investment recommendation and not a strategy promotion.

This run was performed against the production DSE and US research stores from repository commit
`76c3e8a`. It deliberately reused registered hypotheses and frozen thresholds. No threshold was
changed after seeing an outcome. Reconstructed squeeze rows are diagnostic only because they omit
delisted securities and historically unavailable classifications.

## Evidence contract

- A signal formed from completed data; execution was no earlier than the next observable session.
- DSE event diagnostics used 65 bps one-way cost, with 100 bps stress where reported.
- US event diagnostics used 30 bps one-way cost, with 50 bps stress where reported.
- DSEX and SPY were independent benchmarks.
- Chronological train/validation/test results outrank attractive full-period averages.
- Event-level averages were checked against equal-weight signal-date cohorts. This prevents a day
  with many correlated signals from receiving more portfolio weight merely because it emitted more
  rows.
- A reconstructed result cannot be promoted. It can only define a frozen forward hypothesis.

## Foundation snapshot

US foundation audit `data-foundation-v3`, generated 2026-07-25:

- 8,437 research-ready symbols; 8,176 had the latest completed bar (96.91% coverage).
- 16,496,505 projected daily bars and 17,020,884 immutable bar observations.
- Latest completed session: 2026-07-24.
- SEC facts, filings, 13F summaries, FINRA daily short volume and FINRA short interest were present.
- 2,304 symbols remained in onboarding and 4,647 analytics rows had no cap tier.
- Historical point-in-time analytics coverage was not complete.
- 3,251 nonpositive adjusted-close rows existed across `CBIO`, `VATE`, and `DEC`. These rows caused
  the insider backtest to crash and are now explicitly quarantined by the local integrity fix.

## Registered strategy results

| Market | Strategy | Result | Decision |
|---|---|---|---|
| DSE | Deep washout reclaim | Full sample looked positive, but train mean was -1.73%; recent test median was -10.94% and excess was -0.47% | Reject |
| DSE | Panic reclaim | 3 outcomes, all -10.94% | Reject |
| DSE | Activity reclaim | Recent test mean -3.35%, median -8.96%, profit factor 0.50 | Reject |
| DSE | Up-regime high-activity continuation | Negative in train, validation and test; portfolio excess -25.49% | Reject |
| US | Activist 13D book | -8.00% versus +83.68% SPY; Sharpe -0.284 | Reject current construction |
| US | Four-factor sleeve | +12.32% versus +102.93% SPY; beat internal nulls but failed the independent benchmark | Diagnostic only |
| US | Insider-cluster book | Could not complete because invalid adjusted prices entered `StrategyBar` | Blocked pending quarantine rerun |
| US | Liquid trend participation | Bounded 500-name diagnostic did not complete through the remote execution channel | No result |

No registered strategy passed the project's admission gates.

## Squeeze-taxonomy diagnostics

These results use approximately two months of reconstructed states. They are not a historical
backtest and contain survivorship, regime, overlapping-position and point-in-time classification
limitations.

### DSE confirmed compression breakout

| Holding sessions | Observations | Mean net | Median net | Mean DSEX | Mean excess | Median excess |
|---:|---:|---:|---:|---:|---:|---:|
| 5 | 381 | -0.41% | -1.29% | +1.15% | -1.56% | -2.81% |
| 10 | 312 | +1.37% | -0.73% | +2.50% | -1.13% | -3.27% |
| 20 | 241 | +7.05% | +3.99% | +5.38% | +1.67% | -1.63% |

At 20 sessions the event-weighted mean is driven by a minority of large winners. Equal-weighting
each discovery date produces 19 cohorts, +1.01% mean excess, +1.50% median excess and a naive
`t` statistic of only 0.94. This is a forward hypothesis, not an edge.

### DSE confirmed failed-breakdown reversal

The 20-session result was +9.74% net and +3.77% mean excess, but only 11 observations existed and
median excess was -2.89%. Reject as insufficient and skew-driven.

### US confirmed compression breakout

| Holding sessions | Observations | Mean net | Median net | Mean excess to SPY |
|---:|---:|---:|---:|---:|
| 5 | 2,646 | -1.28% | -1.09% | -0.79% |
| 10 | 2,530 | -0.73% | -0.60% | -0.84% |
| 20 | 1,694 | -0.60% | -0.48% | -0.54% |

Reject this implementation. More alerts would only scale a negative expectancy.

### US confirmed failed-breakdown reversal

The event-weighted 10-session result initially looked useful: +1.17% net, +1.37% mean excess and
+1.23% median excess at 30 bps one-way. It did not survive portfolio-style weighting. At the
50 bps stress tier, 224 events collapsed into only 29 equal-weight discovery-date cohorts; mean
cohort excess was -0.47%, median was -0.22%, and the naive `t` statistic was -0.43.

Reject the apparent edge. Correlated signal density created the attractive event-level average.

## Decision

Atlas has no validated profitable strategy today. That is the correct institutional conclusion,
not a reason to loosen gates.

One candidate is allowed to continue as a locked forward experiment:

- `dse_compression_breakout_20d_candidate`
- Entry: next-session open after the existing `confirmed` state.
- Exit: 20 completed sessions, plus the registered portfolio risk controls.
- Costs: 65 bps one-way base and 100 bps stress.
- Benchmark: DSEX over the exact holding window.
- Weighting: one equal-capital signal-date cohort, then equal weight within the cohort.
- No threshold changes until at least 60 independent forward cohort dates exist.
- Promotion additionally requires positive median excess, positive stressed excess, capacity,
  acceptable drawdown, inactive-security coverage and a multiple-testing-adjusted confidence gate.

This candidate must remain separate from current DSE paper capital because its discovery sample is
already contaminated by selection.

## Required next work

1. Deploy the adjusted-price quarantine and rerun the insider-cluster book over the original
   preregistered window.
2. Make cohort-weighted and concurrency-capped portfolio results mandatory for every event agent;
   event-row hit rates are not admission evidence.
3. Complete the bounded US trend diagnostic using a resource-capped batch job with a persisted
   result artifact, not an interactive request.
4. Register distinct forward trials for DSE post-disclosure drift and quality trend-pullback only
   after their point-in-time input contracts are proven.
5. Keep scalp agents blocked. Atlas does not have enough intraday history in either market to make
   a credible scalp claim.
