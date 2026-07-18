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

The current implementation scope is **DSE only**. Existing US research records and code remain
isolated and preserved, but no further US strategy, portfolio, data, UI, deployment, or promotion
work should proceed until the DSE research and portfolio foundation is finished. The eventual
multi-market product should reuse the same contracts with market-specific data, calendars, costs,
constraints and books; it must never reuse DSE state inside a US decision or vice versa.

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

### Intraday foundation implementation

The working tree now has a durable storage contract for future DSE intraday research. Once its
independent migration and ingestion release is deployed, every delayed
quote delivery is retained as an immutable knowledge-time observation, and a separate partitioned
15-minute sampled-bar projection records cumulative session VWAP, counter deltas, completeness,
freshness, and provider-counter regressions. These are labelled sampled delayed observations, not
exchange-native OHLC bars or a real-time tape.

This implementation does not unblock the strategy or create historical coverage retroactively. The
collection clock starts only after that migration and ingestion release are operating. Existing
daily history is reused and does not need to be downloaded from scratch. The
trend-pullback hypothesis remains data-blocked until the Strategy lab's admission report clears the
minimum session history and the remaining universe, constraint-history, and preregistration gates.

The preferred trend idea remains a registered research question, not a discarded intuition. Its
correct test needs stored intraday bars, real session VWAP, effective-dated DSE trading constraints,
corporate-action handling, and realistic next-observable fills.

## Bounded strategy portfolio

Atlas may investigate several independent return sources concurrently, but only through this
bounded portfolio. Do not create overlapping variants merely to increase the chance of finding an
attractive backtest.

| Book | Horizon | State | Decision |
|---|---|---|---|
| `dse_reversal_v1` | EOD swing | Registered diagnostic; no current production Atlas shadow book | Preserve the specification and failed proxy evidence. Do not create or backfill a book unless a new immutable historical admission report passes. |
| `us_breakout_v1` | EOD swing | Active diagnostic Atlas shadow book | Preserve as a separate trend experiment; do not merge its history into Leader Capture. |
| `us_leader_capture_v1` | Multi-month | Candidate diagnostic | Combine point-in-time SEC acceleration with persistent price leadership. Research is allowed; automation is blocked until admission gates pass. |
| `dse_trend_pullback_intraday_v1` | Intraday-to-multiday swing | Data-blocked hypothesis | Persist intraday history first, preregister the rule, then test. Do not paper trade a daily proxy. |
| `dse_quality_value_v1` | Multi-month | Candidate | Rebuild with point-in-time financial publication dates and execution costs before deciding on a separate shadow book. |
| `dse_pead_v1` | Event swing | Data-blocked hypothesis | Wait for deep, timestamped earnings-announcement history and surprise features. |

Three concurrent shadow books per market is the initial maximum. A candidate can occupy a slot only after
its immutable specification and historical diagnostic are stored. A rejected strategy keeps its
record but does not consume an active slot.

The executable registry must assign every strategy an explicit scorer, holding/selection policy,
sizing policy, market and evidence contract. Missing ownership is a runtime error, never a fallback
to the nearest existing strategy. A multi-month book may not silently inherit the weekly full-rank
replacement or low-gross sizing of an EOD swing book.

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

- Atlas `dse_reversal_v1` is a registered deterministic price/liquidity strategy definition that
  avoids historically unavailable fundamental snapshots; no current production shadow book exists.
- Hedge `QualityReversalPortfolio` / `quality_reversal_eod` is a separate agent-paper experiment
  driven by the immutable daily Hedge publication.

They may be compared as evidence, but they are not silently merged and one result must not be
reported as the other's track record.

## Next implementation order

1. Make the portfolio-manager command loop the default operating surface. Keep snapshot-derived
   signal-to-outcome events as an audit projection and introduce an independent, replayable
   accounting ledger before calling cash, position, fee or settlement lineage authoritative.
2. Keep `dse_reversal_v1` registered but inactive. Its January 2025–present historical proxy failed;
   do not create or backfill a shadow book until a new immutable admission report passes.
3. Persist DSE intraday observations as partitioned bars with completeness and freshness metrics;
   do not retain only the latest quote if intraday research is an objective.
4. Write and freeze the trend-pullback experiment before inspecting its holdout.
5. Rebuild the quality-value hypothesis using point-in-time financial publication knowledge.
6. Improve earnings-event history; only then open the PEAD experiment.

This order may change only because a documented data-quality or economic finding changes the
decision, not because a strategy is slow to produce trades or another variant looks more exciting.

The canonical system boundary, Hedge freeze, source-of-truth matrix and independent release gates
are defined in `docs/architecture/atlas-investment-authority.md`.
