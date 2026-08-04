# Bulls of the World AI/ML investment research plan

Recorded: 4 August 2026

Status: **architecture decision and research roadmap; no model is authorized to direct real
capital**.

## 1. Executive decision

Bulls can use machine learning to improve investment decisions, but the correct objective is not
"predict tomorrow's stock price." Financial return signals are weak, unstable and expensive to
trade. The practical objective is to estimate conditional probabilities and cross-sectional ranks,
then combine those views with costs, liquidity, risk and portfolio constraints.

The initial Bulls ML program should therefore build four distinct capabilities:

1. **Return ranking**: rank eligible securities by expected benchmark-relative return over a fixed
   horizon, with calibrated uncertainty and an explicit abstain state.
2. **Event intelligence**: convert filings, disclosures and announcements into point-in-time,
   source-linked structured features. Language models may extract and explain evidence; they do not
   authorize trades.
3. **Risk and tradability forecasts**: estimate volatility, drawdown risk, liquidity, slippage and
   fill probability. These are generally more stable and useful than an exact price forecast.
4. **Portfolio decisions**: combine multiple weak views into risk-sized, cost-aware targets. A model
   score is never an order.

This extends Atlas rather than replacing it. Atlas already has the correct control skeleton:
immutable research specifications, next-observable fills, costs, capacity, benchmarks, shadow
books, risk controls and an audit ledger. ML becomes another registered strategy input inside that
system.

## 2. What institutional investors actually do with AI

The public descriptions from systematic managers are consistent:

- Man AHL says it has used ML components in multi-strategy portfolios since 2014 and describes the
  value as combining many diverse, individually weak information sources. It also stresses that
  finance is noisy and its rules change over time.
  <https://www.man.com/insights/the-rise-of-machine-learning>
- Man reports practical use in faster systematic strategies, trade execution, smart order routing
  and text-based strategies using NLP.
  <https://www.man.com/insights/intro-machine-learning>
- Two Sigma describes a chain of data preparation, independent forecasts, a consensus view,
  portfolio construction that includes risk and trading costs, and systematic execution. It also
  states that it uses tools ranging from ridge regression to NLP, rather than one universal model.
  <https://www.twosigma.com/businesses/investment-management/>
- AQR's research argues that ML in finance remains constrained by low signal-to-noise, changing
  distributions and limited independent observations; economic theory and human expertise still
  matter.
  <https://images.aqr.com/-/media/AQR/Documents/Alternative-Thinking/AQR-Alternative-Thinking-2Q19-Can-Machines-Learn-Finance.pdf>
- AQR also shows why a good forecast can be a bad strategy when turnover and trading costs are not
  optimized jointly with portfolio weights.
  <https://www.aqr.com/insights/research/working-paper/machine-learning-and-the-implementable-efficient-frontier>

The institutional pattern is therefore:

```text
many weak observations
  -> point-in-time features
  -> several independent forecasts
  -> consensus view and uncertainty
  -> transaction-cost-aware portfolio construction
  -> controlled execution
  -> attribution, drift monitoring and retirement
```

AI is used across the whole research and operating loop. It is not normally a chatbot selecting a
ticker and inventing a target.

## 3. What research says about predictive value

There is real evidence that ML can improve cross-sectional return prediction. Gu, Kelly and Xiu
find that nonlinear models can capture interactions missed by linear models, with momentum,
liquidity and volatility among the most important feature families. Their task is risk-premium
measurement across a large panel, not exact next-day price forecasting.
<https://www.nber.org/papers/w25398>

Evidence also exists in emerging markets: nonlinear and interaction-aware models have produced
better out-of-sample cross-sectional results than linear models in a broad multi-country study.
That does not validate a DSE model trained on Bulls data, but it supports testing the hypothesis.
<https://doi.org/10.1016/j.ememar.2023.101022>

The negative evidence is equally important:

- Aggregate market-return prediction often looks strong in-sample and fails to beat simple
  historical-average forecasts out-of-sample.
  <https://www.tandfonline.com/doi/abs/10.1080/14697688.2024.2409278>
- Results depend materially on training windows, data filters, missing-value treatment, portfolio
  construction and model choice.
  <https://www.tandfonline.com/doi/abs/10.1080/0015198X.2024.2388024>
- Trying many variants and publishing the best one creates backtest overfitting. The number of
  trials must be retained and reflected in the statistical assessment.
  <https://papers.ssrn.com/sol3/Papers.cfm?abstract_id=2326253>

Several DSE papers advertise low price RMSE or direction accuracy using a handful of stocks. For
example, one transformer study uses eight DSE stocks and historical daily/weekly prices.
<https://arxiv.org/abs/2208.08300>. That is not sufficient evidence for an investable strategy:
price-level RMSE can be low for a persistent series while next-open, net-of-cost, benchmark-relative
returns are unprofitable. Bulls must test portfolio economics, not chart resemblance.

## 4. Current Bulls data readiness

### DSE

The 3 August 2026 production audit recorded:

- 396 active research-ready symbols and 395/396 latest-session EOD coverage;
- 197,525 daily bars from 27 June 2024 through 3 August 2026;
- current analytics for 396 symbols;
- no adjusted DSE closes;
- no complete historical inactive/delisted universe;
- zero analytics rows certified point-in-time complete; and
- only 11 captured intraday sessions, 10 complete.

Conclusion: DSE is ready for forward feature collection, anomaly detection and diagnostic models.
It is not ready for a capital-bearing supervised return model. The effective independent sample is
roughly the number of market dates, not `symbols x dates`, because securities observed on the same
date are correlated. Raw corporate-action returns and incomplete historical membership can create
false alpha.

### US

The latest repository certification snapshot, dated 24 July 2026, recorded:

- 16,485,582 projected daily bars from 11 July 2016;
- 8,428 active product symbols marked research-ready;
- 4,217,149 point-in-time SEC fact observations;
- adjusted/projected price history and SEC Form 4, 13D and 13F pipelines; and
- incomplete proof of full historical membership, inactive/delisted histories and stable identity
  across the entire test window.

US has enough breadth and history to build diagnostic cross-sectional models once a fresh audit
reconciles bars, adjustments, historical eligibility and identities. It is the first suitable
market for a return-ranking research harness. It is not yet certified for promotion.

### Market isolation

DSE and US must have separate:

- universes and security identities;
- feature snapshots and labels;
- model artifacts, calibration and benchmarks;
- strategies, paper books and promotion decisions; and
- tenant-authorized APIs and storage paths.

US rows must never train a DSE target implicitly, and DSE rows must never appear in US inference.
Cross-market transfer learning is a future experiment and must be registered and compared with a
market-only baseline before use.

## 5. Quantitative trading and universe construction

Quantitative trading means that data, explicit rules and mathematical models determine which
securities are eligible, what constitutes a signal, how much risk to take, how to execute and when
to exit. It does not require AI. Moving-average rules, factor portfolios, statistical arbitrage,
cost models and deterministic risk limits are all quantitative methods. ML is useful when nonlinear
interactions or many weak inputs add value beyond those simpler rules.

Atlas is therefore already a quantitative research and shadow-trading platform. Most current Atlas
signals are deterministic rather than learned, and none has yet proved deployable alpha. The ML
work should strengthen its selection layer without weakening the existing strategy, portfolio and
risk gates.

### Do not train on every listed symbol

Use a two-stage design:

```text
historically eligible and tradable universe
  -> deterministic strategy-specific setup
  -> ML success probability and uncertainty
  -> cost/capacity/risk gate
  -> shadow target or abstention
```

The ML model sees every historical instance that satisfied the frozen setup rule, including failed
trades. Training only on winners or removing securities because they later performed badly would
create look-ahead and selection bias.

### Universe eligibility policy

Eligibility is a data and tradability decision, not an alpha optimization. Every excluded symbol
must carry a dated reason code.

Shared requirements:

- active, historically eligible equity on the decision date;
- permitted security type and stable identity;
- minimum completed-session history required by the feature contract;
- complete, non-stale OHLCV for the decision window;
- no unresolved corporate action or implausible price/volume observation;
- sufficient trading frequency and capacity for the intended position; and
- no active suspension, bankruptcy/delinquency state or other mandate exclusion.

US starting cohorts:

- **Core**: exchange-listed common stocks and ADRs, price at least USD 5, at least 252 sessions and
  20-session median dollar volume at least USD 10 million.
- **Small**: point-in-time market cap USD 300 million to USD 2 billion, price at least USD 2, at
  least 252 sessions and median dollar volume at least USD 2 million.
- **Micro/penny research**: point-in-time market cap USD 20-300 million,
  price at least USD 0.50, at least 180 sessions and median dollar volume at least USD 1 million.
  This is a separate model/risk sleeve, never pooled blindly with Core.
- Exclude OTC securities, warrants, rights, preferreds, units, pre-merger blank-check vehicles,
  unresolved exchange-deficiency/bankruptcy states and recent reverse splits from the first model.

These are conservative starting hypotheses, not permanent magic numbers. Point-in-time market cap
must be proven before cap-based historical cohorts are enabled. Dollar-volume and capacity filters
remain authoritative when market cap is missing.

DSE starting cohort:

- active common equities outside the Z/suspended states;
- at least 180 completed sessions, with new listings handled separately;
- valid adjusted prices once corporate-action processing is certified;
- trades on at least 18 of the prior 20 completed sessions; and
- 20-session median traded value at least BDT 5 million; and
- intended position no larger than 1-2% of expected traded value.

The DSE liquidity threshold should be derived from intended capital. For example, a BDT 100,000
position capped at 2% participation requires at least BDT 5 million daily traded value.
This is more defensible than choosing a turnover cutoff that maximizes a backtest.

### Implemented universe foundation (4 August 2026)

`universe_policy_v1` now implements this boundary as a pure, versioned policy and an immutable
database snapshot:

- every security receives `eligible`, `ineligible`, or `data_blocked`, never a guessed pass/fail;
- product, instrument, status, history, recent-session coverage, trading frequency, price,
  capitalization and median traded-value gates have explicit reason codes;
- DSE and US inputs cannot be evaluated in one batch, and database constraints prevent a cohort
  from crossing its market boundary;
- snapshot policy/input hashes make results reproducible, while append-only triggers prevent a
  prior snapshot from being edited;
- model eligibility is separate from current-screen eligibility and fails closed on incomplete
  listing, bar, capitalization, corporate-action or reverse-split evidence;
- bar reads use bounded 250-symbol batches with at most 300 indexed sessions per symbol rather than
  aggregating the full US bar store; and
- DSE and US workers materialize the current completed-session snapshot outside their critical EOD
  chains, with a completion barrier, concurrency lock and idempotent recovery run.

Operator commands:

```text
uv run python -m ingestion.research_universe_snapshot DSE --json
uv run python -m ingestion.research_universe_snapshot US --json
```

`--force` re-evaluates current projections and creates a new immutable revision only when the input
fingerprint changed. Historical dates are deliberately rejected: using today's security master for
an old date would create survivorship bias. No training or promotable backtest may consume these
snapshots until `model_eligible=true`; current data is expected to remain blocked while the existing
analytics writer reports `point_in_time_complete=false` and reverse-split history is incomplete.

### Strategy-specific setup criteria

Universe eligibility removes untradeable noise. A separate setup rule defines the economic event
the model will evaluate. Initial setup families should remain independent:

- continuation after abnormal but persistent volume and benchmark-relative strength;
- orderly trend pullback with declining sell volume and renewed participation;
- official earnings/disclosure event with measurable surprise or revision;
- insider/activist event for US securities; and
- 52-week-low recovery only when accumulation and balance-sheet evidence agree.

Each family gets its own labels, model and paper sleeve. A model trained on a micro-cap event setup
must not score a large-cap quality strategy as if they were the same problem.

The first useful learned model may be a **meta-labeler**: given a valid deterministic setup, estimate
whether it is likely to reach `+2R` before `-1R`, after costs. It can reject 90% or more of setups.
Selective abstention is a feature, not a failure.

## 6. Prediction targets

Do not train against raw future price. Register one target per model and horizon.

### Primary return target

For security `i`, decision date `t` and horizon `h`:

```text
target(i,t,h) = next-open-to-horizon-close return
              - contemporaneous benchmark return
              - estimated round-trip cost
```

The model predicts a cross-sectional rank or expected residual return. Initial horizons:

- US EOD: 5, 20 and 60 completed sessions;
- DSE EOD after foundation repair: 5, 10 and 20 completed sessions;
- event models: next observable open to 1, 5 and 20 completed sessions.

Each prediction must contain `as_of`, `known_at_cutoff`, horizon, universe, model version,
calibrated uncertainty and an abstention reason when data or expected edge is insufficient.

### Secondary targets

- probability that `+2R` is reached before `-1R` within the registered horizon;
- next-horizon realized volatility and downside semivariance;
- probability of a material gap or limit-lock event;
- expected participation capacity and cost bucket; and
- event materiality, novelty and direction from official disclosures.

Classification accuracy alone is not an investment objective. A 55% accurate model can lose money
after costs, while a lower hit-rate model can be useful if payoff asymmetry and sizing are sound.

## 7. Feature families

Every feature needs `market`, stable `security_id`, `event_time`, `known_at`, source, method version
and restatement lineage.

### Shared EOD features

- residual momentum over 5/20/60/120 sessions;
- trend shape, distance from moving averages and 52-week location;
- realized volatility, ATR, downside volatility and gap behavior;
- relative volume, turnover, Amihud-style illiquidity and zero-trade frequency;
- breadth, sector-relative return and market regime;
- accumulation/distribution proxies such as OBV/CMF, clearly labelled as price-volume proxies rather
  than institutional ownership; and
- capitalization, free float, security status and liquidity capacity.

### US event and fundamental features

- SEC fact level, change, acceleration, margins, cash runway and filing-known timestamps;
- Form 4 transaction type, insider role, cluster size and transaction value;
- activist 13D events and amendments;
- lagged 13F ownership changes, never treated as current positioning;
- filing novelty and risk-language changes;
- FINRA short-volume and short-interest features with their different meanings preserved; and
- confirmed catalyst timing.

### DSE-specific features after repair

- adjusted returns across bonus, rights, split and dividend events;
- financial and ownership observations keyed to first defensible publication time;
- sponsor/director, institution and foreign ownership changes;
- official disclosures, board meetings, earnings and record dates;
- block-trade and turnover features where source coverage is complete; and
- price-limit, category, settlement and liquidity constraints.

Missingness is information but must not be silently imputed. Add missing indicators and compare
with complete-case baselines.

## 8. Model stack

Use the simplest model that survives the test.

### Required baselines

1. historical mean / no-predictability control;
2. benchmark and eligible-universe equal weight;
3. single-factor momentum, value, quality and liquidity ranks;
4. regularized linear/logistic model; and
5. random rank and matched-liquidity null portfolios.

### First ML candidates

- Elastic Net for interpretable sparse effects;
- LightGBM for nonlinear interactions, missing values and CPU-efficient panel training;
- calibrated logistic regression or gradient boosting for barrier probabilities; and
- shrinkage covariance plus constrained optimization for portfolio risk.

Do not start with transformers, reinforcement learning, vLLM or a custom foundation model. The
current data does not justify their parameter count, operational cost or validation burden. A deep
sequence model becomes eligible only if a simpler model has residual failure patterns and the
available independent history can support it.

### NLP and LLM role

FinBERT-class encoders can classify financial text more reliably than generic sentiment models on
domain tasks. <https://arxiv.org/abs/1908.10063>. For Bulls, the first NLP task should be structured
event extraction, not return prediction:

```text
official document
  -> material event type
  -> affected period and numeric changes
  -> novelty versus prior filing
  -> risk/catalyst tags
  -> exact source spans
  -> deterministic feature record
```

Claude or another paid LLM may act as a second-pass verifier and narrative generator when budget
allows. It must receive retrieved source evidence, return a strict schema, expose citations and
abstain on ambiguity. It cannot create numeric prices, silently fill missing data, generate training
labels without audit or bypass portfolio gates. RAG improves evidence retrieval and explanation;
it is not the return model.

Claude is not required for the initial quantitative model. Numeric features, training, inference,
portfolio construction and risk run locally with deterministic Python/CPU jobs. If enabled later,
Claude is called per new material document or ambiguous high-impact event, not per ticker or price
bar. Control cost through cheap deterministic/FinBERT screening, document-hash caching, strict token
limits, batch queues, eligible-universe filtering, daily budgets and a fail-closed circuit breaker.
One verified filing result is stored once and reused across all users and subsequent research.

## 9. Leakage-safe research design

Random train/test splits are prohibited.

1. Freeze universe eligibility and every feature by its historical `known_at` timestamp.
2. Form labels from the next observable open, not the same close used to calculate features.
3. Use expanding or rolling chronological walk-forward folds grouped by date.
4. Purge overlapping label windows and embargo fold boundaries.
5. Fit scalers, imputers, feature selectors and calibration only inside each training fold.
6. Tune on validation folds; keep a final calendar holdout untouched.
7. Include delisted/inactive securities and historical ticker identities.
8. Apply splits, distributions and dividends point-in-time.
9. Run every score through the existing execution engine with costs, spread, capacity, unsettled
   cash, limits and rejected fills.
10. Retain every attempted feature/model configuration in the trial ledger.

Backtest selection bias must be measured with a trial-aware statistic such as Deflated Sharpe and
Probability of Backtest Overfitting, not hidden by deleting failed experiments.

## 10. Evaluation and promotion

### Predictive evidence

- out-of-sample rank IC/Spearman and its stability by fold;
- calibration and Brier score for probabilities;
- monotonic return and risk across prediction buckets;
- performance by regime, cap tier, sector and liquidity bucket;
- feature importance stability and ablation versus simple factors; and
- explicit comparison with every required baseline and null.

### Economic evidence

- net excess return, Sharpe/Sortino and Deflated Sharpe;
- max drawdown, tail loss, turnover, capacity and cost stress;
- profit factor, median trade and winner concentration;
- rejected/unfilled order outcomes; and
- attribution to model view, sizing, timing, costs and constraints.

### Initial promotion gates

A model remains diagnostic unless all of these are true:

- data foundation for that market and horizon is certified;
- positive evidence appears in multiple chronological out-of-sample folds and the untouched
  holdout, not one favorable regime;
- the portfolio beats simple factor, equal-weight and matched-liquidity controls after normal and
  stressed costs;
- results are not dependent on one year, sector, cap tier or a few extreme winners;
- calibration and feature behavior remain stable enough to support sizing;
- trial-aware false-discovery assessment passes the registered threshold;
- at least 120 completed forward market sessions are collected without changing the rule; and
- drawdown, turnover, concentration and capacity remain inside the pinned mandate.

Passing these gates authorizes only a shadow strategy promotion review. Real capital remains a
separate owner decision.

## 11. Production architecture

```text
Exchange, SEC, DSE, FINRA and official sources
  -> immutable observations and source artifacts
  -> market-bound point-in-time feature snapshots
  -> market-bound label builder
  -> reproducible walk-forward training jobs
  -> experiment and trial ledger
  -> model registry: artifact + code + data fingerprints + model card
  -> post-close/event inference with abstention
  -> registered Atlas strategy adapter
  -> cost/capacity-aware portfolio construction
  -> risk controls and shadow execution
  -> outcomes, attribution, drift and kill switches
```

Technology fit for the current server and codebase:

- PostgreSQL remains the authoritative online point-in-time and decision store;
- Parquet plus Polars supplies bounded offline training matrices;
- S3 stores immutable model artifacts and dataset manifests;
- scikit-learn provides baselines/calibration and LightGBM provides the first nonlinear model;
- the existing worker/systemd model schedules bounded CPU training and inference;
- the existing Atlas trial, strategy, portfolio and audit tables remain the control plane; and
- a small Postgres-backed model registry is preferable to operating MLflow/Feast/Kubernetes now.

Add MLflow or a dedicated feature-store service only when concurrent researchers, artifact volume
or online latency makes the simpler design inadequate.

Model-risk governance should follow the same principles used in regulated institutions: sound
development, independent effective challenge, documented limitations, ongoing monitoring and
decommissioning. The US banking agencies revised this guidance in 2026; Bulls is not a bank, but
the control pattern is appropriate for financial models.
<https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm>

## 12. Atlas product experience

### Today

Show at most a small, risk-budgeted decision set:

- model horizon and as-of cutoff;
- candidate rank and calibrated probability/range;
- expected excess after estimated cost;
- top supporting evidence and counter-evidence;
- uncertainty, data quality and abstention reason;
- trigger, invalidation and next observable execution; and
- whether it is research, a shadow target, a filled position or an exit.

"No qualified opportunity" is a correct and useful daily output.

### Strategy Lab

Expose the hypothesis, immutable target definition, model card, data window, trial count, baselines,
walk-forward folds, holdout, costs, capacity, calibration, feature stability, drift, forward results
and exact reasons for diagnostic/paused/promoted/retired state.

### Company Research

Show the model view as one bounded section beside fundamentals, filings, ownership, catalysts,
risks and the counter-thesis. Never present a raw score as a guaranteed confidence percentage.

### Portfolio and Risk

Show the contribution of each model sleeve, benchmark-relative performance, current exposures,
factor/cap/sector concentration, liquidity, drawdown, rejected targets and model interventions.

## 13. Delivery plan

### Phase 0 - foundation and contracts (P0)

1. Produce a fresh US data-foundation certification artifact.
2. Implement DSE corporate-action adjustments and historical security-status/universe history.
3. Establish defensible `known_at` lineage for DSE fundamentals, ownership and announcements.
4. Freeze versioned feature and label contracts for US and DSE.
5. Add dataset manifests containing row counts, coverage, hashes and exclusion reasons.

Exit: a historical date can be reconstructed without using information learned later.

### Phase 1 - ML research platform (P0)

1. Add market-bound feature snapshots and label tables.
2. Build Parquet/Polars exports and reproducible walk-forward folds.
3. Add model artifact/model-card registry and trial fingerprints.
4. Add deterministic baseline, null and leakage tests.
5. Add drift and inference audit records.

Exit: the same code/data/config reproduces the same predictions and portfolio result.

### Phase 2 - first US diagnostic models (P1)

1. Train 5/20/60-session residual-return rankers: Elastic Net versus LightGBM.
2. Train volatility/downside and liquidity/cost models.
3. Build event studies for Form 4 clusters and 13D events.
4. Run cost-aware long-only top-bucket portfolios and all controls.
5. Keep US short execution blocked until point-in-time borrow, locate, fee and recall data exist.

Exit: publish an honest pass/fail research report. Do not weaken gates after seeing results.

### Phase 3 - DSE diagnostic models (P1, after Phase 0)

1. Continue the already frozen Daily Shortlist forward experiment.
2. Train only simple 5/10/20-session cross-sectional baselines at first.
3. Test whether ownership, official disclosure and price-volume features add incremental value over
   momentum/liquidity controls.
4. Evaluate by next-open fills, DSEX-relative return, DSE costs, price limits and capacity.

Exit: either register a fixed shadow candidate or record a rejection. No result is also a result.

### Phase 4 - event intelligence (P1)

1. Add source-linked structured extraction for SEC and DSE disclosures.
2. Validate event type, numeric extraction, novelty and direction on a labelled gold set.
3. Add an LLM skeptic/verifier only after deterministic extraction metrics are visible.
4. Feed verified event features into return models through their own registered ablation trial.

Exit: event features demonstrably add out-of-sample value or remain research-only.

### Phase 5 - forward shadow operation (P0 for promotion)

1. Operate no more than three economically distinct model sleeves per market.
2. Recompute post-close and on material official events; never overwrite prior predictions.
3. Track prediction decay, calibration, costs, rejected fills and model drift daily.
4. Pause automatically on stale data, schema drift, calibration failure or mandate breach.
5. Collect at least 120 untouched forward sessions before any promotion review.

### Phase 6 - later data investments (P2)

- US options only after licensing and point-in-time chain quality are established;
- US borrow/locate data before any executable short model;
- deeper DSE adjusted and inactive history;
- intraday/order-book models only after timestamped trade/quote depth is sufficient; and
- alternative data only when its economic mechanism, legal right and incremental value are tested.

## 14. Implemented baseline and next build

The market-bound current-session universe policy, causal feature/label contract, reproducible
ridge baseline harness and tenant-bound Strategy Lab model audit are implemented. The remaining
foundation work is **historical point-in-time reconstruction**; a browser widget does not remove
that gate.

Before fitting a return model:

1. reconstruct historical listing membership and stable identity from append-only observations;
2. certify adjusted bars and corporate-action/reverse-split history by decision timestamp;
3. materialize dated capitalization without backfilling today's value into the past;
4. make every feature and label carry `as_of`, `known_at_cutoff`, source and method version; and
5. require the baseline harness to request an explicit universe snapshot with
   `require_model_eligible=true`.

Recommended first experiment after the US foundation passes:

```text
name: us_eod_cross_section_rank_v1
universe: historically eligible common stocks and ADRs
decision: completed US session close
entry: next observable open
horizons: 5 and 20 sessions
target: SPY-relative net return
models: Elastic Net and LightGBM
controls: momentum-only, equal-weight, matched-liquidity, random-rank
portfolio: long-only top bucket, volatility scaled, cost/capacity constrained
status: diagnostic only
```

### 2026-08-04 production diagnostic

Atlas evaluated the linear baseline on the production server without copying the database:

- 5,470 currently active product-eligible U.S. common-stock/ADR histories;
- 955,275 five-session and 237,566 twenty-session causal observations;
- completed-close features, next-session-open entry, SPY-relative labels and explicit doubled-cost
  stress;
- 2016-2022 discovery, 2023-2024 validation and 2025 onward untouched holdout; and
- current survivors only, because historical listing/delisting and corporate-action evidence is
  not yet point-in-time complete.

Both horizons failed the frozen economic gate:

| Horizon | Holdout mean net | Doubled-cost mean | Annualized net | Sharpe | Max drawdown | Decision |
|---|---:|---:|---:|---:|---:|---|
| 5 sessions | -0.12% | -0.22% | -5.94% | -0.44 | -24.26% | rejected |
| 20 sessions | -0.55% | -0.66% | -6.96% | -0.78 | -13.87% | rejected |

The artifact remains immutable under `var/research/us-eod-rank/<run>/model-evaluation.json`. Atlas
serves only a validated, compact projection on `/institutional-research/model-experiments/latest`;
the requesting tenant market must match the artifact market. Strategy Lab displays the certified
universe, chronological metrics, momentum control, fitted drivers, limitations and exact promotion
blockers. This experiment creates no candidate, target, paper trade or order.

The next model iteration must be a new preregistered hypothesis, not threshold tuning against this
holdout. First repair dated listing, capitalization, delisting and corporate-action evidence; then
test an economically motivated nonlinear challenger and event-feature ablations against this frozen
linear baseline.

For DSE, complete the foundation repair and forward Daily Shortlist experiment in parallel. Do not
train a high-capacity model merely because 197,000 bar rows look large; the calendar history and
market regimes remain short.

## 15. Capital conclusion

ML can create value for Bulls, especially in ranking, event processing, risk forecasting and
portfolio construction. It cannot make stock moves reliably predictable, guarantee profit or cure
bad point-in-time data. The likely edge is a disciplined combination of many weak, market-specific
signals with aggressive abstention and risk control.

The correct owner expectation is:

```text
better triage + better calibrated odds + better sizing + fewer bad trades
```

not:

```text
an AI ticker in the morning that can be bought blindly
```

That is a buildable, institution-grade direction. Whether it produces alpha is an empirical result
that Bulls must earn through the gates above.
