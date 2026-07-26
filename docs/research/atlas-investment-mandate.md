# Atlas investment mandate

Recorded: 18 July 2026

This document is the durable owner mandate and strategy-governance contract for Atlas. Read it
before adding, changing, activating, merging, or presenting an investment strategy.

Atlas's portfolio-manager workflow and institutional research basis are defined in
`docs/research/institutional-investment-operating-model.md`. The two documents are jointly
normative: this mandate governs strategy admission; the operating model governs the product loop.

## Owner mandate

- Build from zero with institutional discipline. Capital preservation and evidence quality come
  before growth, activity, strategy count, or attractive backtest returns.
- The owner is especially interested in riding a strong trend after a controlled micro-pullback to
  a meaningful reference such as an EMA or session VWAP. This is a research preference, not an
  instruction to force a trend strategy into production.
- The owner wants to learn the existing reversal book step by step and does not want a long forward
  observation period wasted. A small number of genuinely different paper experiments may collect
  evidence in parallel.
- Strategy selection is delegated to the research process. Atlas must reject an idea, including an
  owner-preferred idea, when the data or validation does not support it. No strategy is preferable
  to a misleading strategy.
- Atlas is intended to become an institution-grade research and risk system. It must not optimize
  for entertainment, frequent signals, or the appearance of intelligence.

## Current decision

Do not activate a generic DSE momentum, volume-breakout, or daily EMA-pullback paper strategy.

The production data checked on 18 July 2026 contains 192,776 DSE daily bars for 401 symbols from
27 June 2024 through 16 July 2026. Adjusted closes are not populated. The 15-minute quote pipeline
keeps the latest snapshot for 396 symbols but does not retain an intraday history. Inactive and
delisted history is incomplete. This is enough for forward EOD experiments, but not enough to make
an institution-grade claim about an intraday micro-pullback edge or performance across regimes.

Existing research also rejects the available daily substitutes:

- the tested daily 9-EMA pullback lost in both chronological halves;
- the generic volume breakout and pullback-in-uptrend books lost money;
- the costed 2026 high-volume continuation test underperformed DSEX;
- the strict flat-base detector remains a descriptive watchlist, not a validated entry signal.

The preferred trend idea remains a registered research question, not a discarded intuition. Its
correct test needs stored intraday bars, real session VWAP, effective-dated DSE trading constraints,
corporate-action handling, and realistic next-observable fills.

## Bounded strategy portfolio

Atlas may investigate several independent return sources concurrently, but only through this
bounded portfolio. Do not create overlapping variants merely to increase the chance of finding an
attractive backtest.

| Book | Horizon | State | Decision |
|---|---|---|---|
| `dse_reversal_v1` | EOD swing | Active diagnostic Atlas shadow book | Keep collecting immutable forward evidence. Explain its entries and failures; do not call it validated. |
| `dse_compression_breakout_20d_v1` | EOD swing | Paused after failed historical diagnostic | Preserve the trial and book audit trail, but form no new targets. After the 2026-07-26 archive correction it returned +4.24% at measured costs versus +8.01% for DSEX, an excess return of -3.77 percentage points. The improvement does not pass the benchmark gate or convert reconstructed evidence into forward evidence. |
| `dse_selective_compression_v1` | EOD swing | Not admitted after first diagnostic | The fixed rule evaluated 186 confirmations but qualified none. Preserve the run; do not weaken gates using validation/test outcomes and do not create a forward book. Any v2 must justify its changes from training-only feature availability and register as a new attempt. |
| `dse_demand_signature_v1` | EOD watch / swing research | Rejected as an entry strategy | Combined price and demand trajectories improved holdout sharp-move identification by +14.57pp versus the eligible base rate, but next-open execution lost 1.30% per candidate after costs and the holdout slot book lost 17.95% versus DSEX +11.62%. Preserve it as a research lead only; no paper targets. See `dse-demand-signature-2026-07-26.md`. |
| `dse_keltner_momentum_v1` | EOD trend | Rejected as an entry strategy | The preregistered next-open `EMA(20) +/- 2 * ATR(20)` rule returned -0.37% mean and -4.11% median per holdout trade, trailed DSEX by 1.71 percentage points on signal-date cohorts and had a 0.92 profit factor. Both robustness neighbors failed. Keltner position may be a descriptive feature, not an Agent Decision. See `keltner-channel-result-2026-07-26.md`. |
| `dse_trend_pullback_intraday_v1` | Intraday-to-multiday swing | Data-blocked hypothesis | Persist intraday history first, preregister the rule, then test. Do not paper trade a daily proxy. |
| `dse_quality_value_v1` | Multi-month | Candidate | Rebuild with point-in-time financial publication dates and execution costs before deciding on a separate shadow book. |
| `dse_pead_v1` | Event swing | Data-blocked hypothesis | Wait for deep, timestamped earnings-announcement history and surprise features. |

Three concurrent DSE shadow books is the initial maximum. A candidate can occupy a slot only after
its immutable specification and historical diagnostic are stored. A rejected strategy keeps its
record but does not consume an active slot.

The squeeze monitor remains broad research inventory. Its `forming` and `confirmed` rows are not
orders and are not copied into Agent decisions. Only a target produced by an admitted registered
strategy appears there.

## US research decision ledger

The same admission rules apply to US research. A spectacular reconstructed case does not override
the population result.

| Experiment | Horizon | State | Decision |
|---|---|---|---|
| `us_former_runner_reactivation_v1` | EOD watch for a three-session expansion | Rejected | The fixed former-runner, deep-pullback and repeated-volume sequence correctly identified STAK on 23 July 2026 before its next stored expansion, but only 13.79% of 87 completed historical episodes reached the +20% opportunity barrier versus 14.25% for date/liquidity/volatility-matched controls. The 2026 retrospective subset was 0/17. Do not schedule it, create Agent Decisions, or paper trade it. `SLND` was an unresolved 24 July observation, not a recommendation. See `us-former-runner-reactivation-2026-07-26.md`. |
| `us_keltner_momentum_v1` | EOD trend, long and diagnostic short | Rejected | The preregistered long rule lost 0.65% on average in the 2025-2026 holdout, with a -3.30% median, -1.82 percentage-point cohort excess and 0.89 profit factor. Diagnostic shorts lost 2.68% with a 0.58 profit factor and cannot be executed without borrow evidence. Both robustness neighbors failed. See `keltner-channel-result-2026-07-26.md`. |

Atlas has no stored US intraday bars, verified free-float history, point-in-time borrow availability
or cost-to-borrow, halt/order-book tape, or independent external social-velocity history. The
former-runner hypothesis cannot be repaired by substituting daily OHLCV for those missing inputs.
Any successor must wait for the required data, receive a new experiment key, and be preregistered
before another holdout is inspected.

Do not transfer the US sequence mechanically to DSE. DSE price limits, liquidity, settlement,
corporate actions and raw-close contamination make a one-session `+40%` runner definition
non-equivalent. The existing DSE demand-signature study is the relevant evidence: volume and price
structure improved sharp-move identification, but the tested next-open strategy lost money.

## Strategy admission process

1. **Economic thesis:** state who is forced, slow, constrained, or behaviorally biased and why the
   effect should survive costs. An indicator pattern alone is not a thesis.
2. **Immutable specification:** freeze universe, features, signal time, eligible fill, exits,
   benchmark, costs, capacity, risk limits, and kill criteria before viewing holdout results.
3. **Data audit:** require point-in-time availability, corporate-action safety, inactive/delisted
   coverage, market-calendar correctness, and explicit missing-data behavior. Missing means abstain.
4. **Historical diagnostic:** use chronological train, validation and untouched test windows;
   compare with simple baselines; report all attempted variants and stressed costs.
5. **Forward shadow:** execute only at the next observable eligible price. Persist intended,
   constrained, rejected and filled orders so capacity or cash shortages are measurable.
6. **Promotion:** require the existing Atlas historical gates plus at least 60 forward sessions,
   10 executions, positive benchmark-relative return and maximum drawdown no greater than 15%.
   Eligibility is not permission to trade real capital.
7. **Kill or revise:** stop new entries when data quality fails, the economic mechanism disappears,
   drawdown brakes fire, or predefined forward gates fail. A revision receives a new strategy key.

Multiple-testing controls are mandatory. Record every hypothesis and variant, including failures;
use false-discovery controls or a deflated performance statistic when comparing many trials. Never
select only the best-looking backtest from an undocumented search.

## Trend-pullback research contract

The next trend study, when intraday data exists, must test a mechanism rather than the phrase
"buy the dip." At minimum it should distinguish:

- established trend strength from one-day price spikes;
- orderly contraction from distribution, limit-lock behavior, or an illiquid gap;
- pullback depth and duration relative to volatility;
- declining volume during the pullback and renewed participation on reclaim;
- session VWAP and intraday EMA behavior from daily approximations;
- broad-market and sector regime;
- next-observable execution, spread/slippage, circuit constraints, ADV capacity and T+2 cash use;
- invalidation below the structural pullback low and an explicit maximum holding horizon.

Low-cap and micro-cap results must be reported separately. DSE low-cap momentum has produced severe
historical drawdowns, so those tiers require stricter liquidity, extension and execution gates.

## Product and operator rules

- Research urgency, thesis confidence, strategy expected value, and portfolio risk are separate
  quantities. Never combine them into a universal score.
- Each paper book must show: strategy name and version, why a position qualified, signal timestamp,
  intended and actual fill, current thesis state, invalidation, fees, cash/capacity rejections,
  benchmark, drawdown, and next scheduled evaluation.
- Show new targets, executions, exits and rejected orders as separate events. A target is not a
  trade, and a qualified company is not a buy signal.
- Maintain strategy-specific archives by market session. Users must be able to compare today with
  prior runs without rewriting historical decisions.
- DSE and US strategy state, data, calendars, costs and books remain tenant- and market-scoped.

## Naming boundary

Do not conflate the two existing reversal systems:

- Atlas `dse_reversal_v1` is a deterministic price/liquidity shadow strategy and currently avoids
  historically unavailable fundamental snapshots.
- Hedge `QualityReversalPortfolio` / `quality_reversal_eod` is a separate agent-paper experiment
  driven by the immutable daily Hedge publication.

They may be compared as evidence, but they are not silently merged and one result must not be
reported as the other's track record.

## Next implementation order

1. Make the portfolio-manager command loop the default operating surface and preserve exact event
   lineage from signal through target, constraint, fill, position, exit and outcome.
2. Keep `dse_reversal_v1` running unchanged long enough to build honest forward evidence.
3. Persist DSE intraday observations as partitioned bars with completeness and freshness metrics;
   do not retain only the latest quote if intraday research is an objective.
4. Write and freeze the trend-pullback experiment before inspecting its holdout.
5. Rebuild the quality-value hypothesis using point-in-time financial publication knowledge.
6. Improve earnings-event history; only then open the PEAD experiment.

This order may change only because a documented data-quality or economic finding changes the
decision, not because a strategy is slow to produce trades or another variant looks more exciting.
