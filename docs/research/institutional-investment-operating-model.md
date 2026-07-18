# Atlas institutional investment operating model

Recorded: 18 July 2026

## Product decision

Atlas is a portfolio-first, strategy-driven, evidence-backed operating system for a solo portfolio
manager. It is not a research-queue product, a general chatbot, a collection of market widgets, a
broker, or evidence that any strategy will produce future returns.

The daily product must answer, in order:

1. What changed in the market, evidence, and portfolio?
2. Which registered strategies created or removed a target?
3. What will be bought, sold, resized, or rejected at the next eligible paper execution?
4. What portfolio, liquidity, concentration, drawdown, and data risks require action?
5. What did each strategy contribute after benchmark, costs, capacity, and constraints?

Company research supports these decisions. Investigation urgency never substitutes for a strategy
signal, and an autonomous company conclusion never bypasses portfolio construction or risk.

## Institutional research basis

The operating model follows a common institutional sequence rather than copying one vendor UI:

- The CFA portfolio-management process begins with written objectives and constraints, then moves
  through execution and a feedback loop. Risk capacity, liquidity, horizon, legal restrictions,
  benchmark, and rebalancing policy belong in the mandate before security selection.
  https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/basics-of-portfolio-planning-and-construction
- Point72 trains analysts in idea generation, market forces, management meetings, data analysis,
  accounting, modeling, stock coverage, pitching, and regulatory compliance. The output is an
  independently defensible research process, not an indicator score.
  https://point72.com/point72-academy/
- Citadel describes deep fundamental research and financial analysis followed by careful portfolio
  construction and disciplined risk management. Quantitative researchers provide performance
  analysis, insights, and risk flags to investment teams.
  https://www.citadel.com/what-we-do/equities/
- Two Sigma describes the systematic chain as data sourcing and preparation, modeling persistent
  signals, portfolio construction, and execution. Its allocation step combines views with trading
  costs and risk rather than trading every standalone forecast.
  https://www.twosigma.com/businesses/investment-management/
- Man AHL describes a measured idea-to-strategy process: simulation across long histories and
  environments, followed by live paper trading before risking capital.
  https://www.man.com/sites/default/files/uploads/embed/ahl-landing-page-who-is-ahl-1/index.html
- AQR emphasizes portfolio construction, risk management, cost control, risk allocation, genuine
  diversification, and a systematic drawdown-control method.
  https://www.aqr.com/Insights/Research/Trade-Publication/The-Alpha-in-Portfolio-Construction
- CFA performance measurement requires an ex-ante benchmark, excess-return calculation,
  attribution, and risk analysis as part of the investment feedback loop.
  https://rpc.cfainstitute.org/blogs/enterprising-investor/2012/performance-measurement-and-attribution-the-what-why-and-how-of-the-investment-management-process
- Man Group's quant-manager criteria include independent risk monitoring, diversifying strategies,
  joined-up strategy/portfolio/execution/risk design, broad regime history, test trading, and an
  honest record of failed research.
  https://www.man.com/insights/intro-machine-learning

These sources describe processes and principles, not a guaranteed recipe for performance. Atlas
must test each market-specific hypothesis using its own point-in-time data and execution reality.

## Operating loop

```text
Mandate and risk budget
  -> Point-in-time data and market state
  -> Registered economic hypothesis
  -> Historical simulation and falsification
  -> Strategy signal or abstention
  -> Company/catalyst/forensic evidence check
  -> Portfolio target construction
  -> Risk, cash, liquidity and capacity constraints
  -> Next-observable paper execution or explicit rejection
  -> Position monitoring, invalidation and exit
  -> Benchmark-relative attribution and research memory
  -> Strategy scale, pause, revise or retire decision
```

Every transition is durable and auditable. A signal is not a target, a target is not an order, an
order is not a fill, a fill is not a good investment, and a profitable trade is not proof of an
edge.

## Product information architecture

### Today

The default portfolio-manager command center. It shows evidence cutoff, last/next completed cycle,
risk interventions, next-session targets, completed paper fills, strategy-book posture, catalysts,
and research requiring attention. Risk precedes targets; targets precede fills; research is clearly
labelled as non-order work.

### Portfolio and risk

Strategy-specific NAV and benchmark, cash, exposure, holdings, target transitions, orders, fills,
fees, capacity rejections, drawdowns, factor/sector concentration, and intervention history.

### Strategy lab

Immutable hypotheses, data eligibility, economic mechanism, variants attempted, train/validation/
test results, stressed costs, capacity, correlation to other books, paper status, promotion gates,
and retirement history.

### Research

An evidence inbox, company dossiers, catalysts, financial models, variant view, counter-thesis,
forensic risks, expected evidence, and thesis invalidation. Research can support or reject a setup;
it cannot create discretionary orders outside a registered strategy.

### Operations and audit

Automation policy, data freshness, run ledger, model/method versions, evidence fingerprints,
research memory, security/tenant audit, and failure recovery. These controls are not primary
investment navigation.

## Current implementation status

Implemented foundations:

- market-bound deployments, authorization, RLS and tenant assertions;
- point-in-time evidence contracts and source-linked company research;
- registered deterministic backtests with next-session fills, costs, capacity, stops and brakes;
- no-broker shadow books with persisted NAV, targets, fills, fees and interventions;
- autonomous evidence review, skeptic/verifier stages and immutable outcome observations;
- versioned investment mandates pinned to each trial and paper book, so later policy changes do not
  rewrite historical decisions;
- preregistered strategy trials with immutable specifications, family attempt sequencing, and an
  explicit diagnostic gate for repeated testing;
- append-only decision lineage for new reconciled sessions, from strategy intent through target,
  constraint, fill, position and measured outcome;
- point-in-time concentration, liquidity, correlation and deterministic stress diagnostics against
  each book's pinned mandate;
- performance attribution that labels exact, proxy and unavailable components rather than
  manufacturing precision;
- a default Investment Command screen that composes current books, lifecycle decisions, catalysts,
  and the research inbox without collapsing their meanings.

Material gaps before Atlas is an institution-grade investment system:

- no Atlas strategy has passed all historical and forward promotion gates;
- DSE adjusted prices, inactive/delisted history, intraday history and multi-regime depth are not
  complete;
- portfolio risk now includes observed correlation, capacity and deterministic stresses, but does
  not yet include a validated market/sector/style factor model or covariance shrinkage;
- attribution measures portfolio, benchmark, fees and compounding exactly and provides a market
  exposure proxy, but selection, timing, sizing and constraint opportunity cost remain unavailable
  without retained counterfactual and arrival-price data;
- legacy experiments are explicitly reconstructed rather than called preregistered, and repeated
  strategy-family attempts remain diagnostic until a statistical multiple-testing adjustment is
  implemented;
- historical causal lineage is not invented for old books; their append-only ledger begins on the
  next reconciled session;
- there is no broker execution and no authorization to represent paper results as investable.

## Next validation order

1. Operate a small set of economically distinct paper books through enough unseen sessions to test
   the decision ledger, mandate controls and failure recovery.
2. Repair point-in-time price/fundamental history and delisted-universe coverage before accepting a
   promotion result.
3. Add a validated market/sector/style factor model and covariance shrinkage only after the input
   history passes those gates.
4. Retain arrival-price and rejected-target counterfactuals so timing, sizing and constraint
   attribution can be measured rather than inferred.
5. Apply a documented multiple-testing adjustment, then retire failed strategy families without
   deleting their trials or paper results.
6. Consider real capital or external claims only after historical and forward promotion gates pass.

New pages or models must strengthen this loop. Do not add isolated widgets, unregistered signals,
unexplained scores, or automated orders.
