# TrendSpider product study and Bulls of the World strategy

**Date:** 2026-08-10
**Status:** Product and architecture decision
**Scope:** TrendSpider's current product, its practical value to Bulls of the World, and a build/use/avoid roadmap for Bulls of Dhaka, Bulls of Wall Street, and Atlas.

## Research method and confidence

This review combines TrendSpider's official pricing, product, developer, support, and data documentation with a repository-level inventory of Bulls Portal and Atlas. Product availability and documented limitations have high confidence. Claims about performance, speed, or institutional adoption are vendor claims unless separately measured.

No TrendSpider strategy performance was accepted as evidence of an edge. Prices, limits, bundled data, and AI allowances can change and must be rechecked before purchase. A hands-on trial is still required to validate usability, latency, data quality, and compatibility with Bulls workflows.

## Executive decision

TrendSpider is a strong analyst workstation. Its defensible advantage is not a single indicator, AI chat panel, or dark terminal layout. Its advantage is a reusable market-condition model connected to a complete workflow:

`chart -> scan -> alert -> backtest -> forward monitor -> optional automation`

The same data and condition can be inspected visually, searched across a universe, monitored continuously, and tested historically. This removes substantial analyst friction.

Bulls should learn from that architecture, but should **not clone TrendSpider feature for feature**.

### Recommended position

1. **Use TrendSpider now as an owner-side US research and UX benchmark.** It can accelerate visual validation, chart review, and prototyping while Bulls' own research platform matures.
2. **Keep Bulls as the system of record.** Atlas must remain authoritative for tenant boundaries, evidence lineage, point-in-time research, strategy admission, portfolio risk, and measured outcomes.
3. **Build one typed Bulls condition engine.** A condition authored once should power chart overlays, scans, alerts, historical tests, and paper-strategy candidates.
4. **Build an Atlas Investigation Workbench.** It should synchronize chart, events, fundamentals, filings, ownership, catalysts, research conclusions, and portfolio context around one ticker and one point in time.
5. **Do not use an LLM across the full universe.** Deterministic jobs should narrow thousands of symbols to a small evidence-qualified set. AI should investigate user-selected or shortlisted cases with cited tools and a strict budget.
6. **Do not make TrendSpider a production data dependency without a commercial agreement.** Its documented custom-data API is primarily for uploading data into a user's TrendSpider account, while alerts can leave via webhooks. That is not a general external market-data API or redistribution license.

The product opportunity is not "a cheaper TrendSpider." It is:

> An evidence-first research operating system that combines professional chart workflows with DSE-native intelligence, US small/micro-cap regulatory evidence, reproducible research, and portfolio admission controls.

## Delivered foundation: research conditions v1

The first implementation slice is now present in the repository. It deliberately stops at evidence collection and analyst monitoring; it does not create strategy targets, paper orders, or live orders.

### Shared condition engine

- one versioned analytics registry defines trend alignment, participation expansion, and controlled-pullback context;
- the same definitions produce current matches, per-check explanations, state transitions, and 1/5/20/60-session follow-through measurements;
- historical reconstruction and production-forward observations remain separate evidence modes;
- favorable and adverse excursions are measured from the observation close without using future data to form the observation;
- DSE and US jobs run through the same typed engine while retaining independent tenant, market, universe, currency, and scheduling boundaries.

### Evidence and operations

- immutable condition transitions and dated calibration summaries are persisted with condition and methodology versions;
- scheduled completed-session jobs compile forward observations for each market;
- persistence is chunked and idempotent, and historical backfills never send alerts;
- alerts are explicit per-user, per-ticker, per-condition subscriptions and fire only for a new forward transition;
- the API derives tenant scope from the authenticated workspace and applies it to every read and write.

### Atlas workbench

The new **Condition scanner** route provides:

- condition, observation-state, and capitalization filters;
- current matches ordered by observation recency and trading-capacity context;
- a plain-language research story and every actual value against the registered threshold;
- clearly separated reconstructed and forward calibration panels;
- 1/5/20/60-session median return, positive-close rate, benchmark-relative return, maturity, and pending counts;
- company-research navigation and explicit observation-alert controls;
- responsive light and dark layouts for both Bulls of Dhaka and Bulls of Wall Street.

The company dossier now also contains an **Investigation Workbench v1**. It composes the
existing tenant-bound dossier facts into one synchronized analyst surface rather than creating a
second product or another data contract:

- a primary completed-session price chart with daily and weekly aggregation, price/benchmark
  modes, 3/6/12-month windows, EMA layers, support/resistance, evidence markers, condition
  transitions, and paper-portfolio events;
- a research-condition rail whose selection updates both the chart annotation and the definition,
  actual value, registered threshold, limitation, and observed/not-observed state in the inspector;
- inspector views for official evidence, fundamentals, the bounded autonomous analyst record, and
  explicit missing-data states;
- a timestamped evidence timeline that keeps condition transitions, official records, and
  portfolio events distinct while sharing one point-in-time context;
- balanced, chart-focus, and evidence-focus layouts saved locally under a tenant-specific key;
- explicit daily-source labeling on weekly bars and moving-average overlays. Weekly rendering is
  aggregation of stored daily records, not an intraday or native weekly data claim.

The workbench does not create candidates, targets, fills, probability estimates, or analyst facts.
It is an investigation surface over the existing dossier, condition registry, and paper-ledger
contracts. DSE and US builds remain hard-bound to their own tenant, market, site, portal, and API
domains.

### Remaining admission work

This foundation answers *what matched, why, and what historically followed*. It does not establish a profitable edge. Before any condition can influence a strategy book, it still requires point-in-time universe reconstruction, corporate-action-complete data, cost/capacity modelling, regime and segment stability, untouched holdout validation, forward evidence, and the existing Atlas strategy-promotion controls.

## What TrendSpider is

TrendSpider combines six product layers:

| Layer | What it provides | Why users value it |
|---|---|---|
| Charting | Multi-timeframe charts, automated trendlines, indicators, patterns, heatmaps, volume-based views, event overlays | Fast visual diagnosis without manually drawing every object |
| Discovery | Multi-factor scanner, smart watchlists, maps, flows, technical and non-technical filters | Converts a hypothesis into a searchable universe |
| Monitoring | Dynamic alerts, multi-factor alerts, scheduled scans, notifications, webhooks | Removes the need to stare at charts continuously |
| Validation | Strategy Tester, multi-symbol tests, costs/slippage inputs, forward testing and exports | Makes a rule falsifiable instead of relying on screenshots |
| Automation | Strategy bots and outbound webhooks, including connections to execution tooling | Turns confirmed rules into repeatable operations |
| AI and scripting | Sidekick, visual scripting, JavaScript studies, AI-assisted indicator creation | Lowers the effort required to query data and create tools |

TrendSpider's [market-data catalog](https://trendspider.com/marketdata/) explicitly presents the same datasets as reusable in charting, scanning, strategy development, and alerting. This cross-surface reuse is the most important product lesson for Bulls.

## What the attached workspace demonstrates

The supplied PLTR screenshot is effective because every panel shares one ticker context:

- business KPIs and narrative on the left;
- price, volume, indicators, and drawn structure in the center;
- analyst estimates, news, and seasonality on the right;
- fundamental trends and peer/market context below;
- an AI assistant that can reason over the active workspace.

The value is **linked context**, not maximum information density. The layout answers several questions without page changes:

1. What is price doing?
2. What business or event evidence may explain it?
3. Is the move unusual relative to history or peers?
4. What would invalidate the thesis?
5. Can the rule be scanned, monitored, or tested?

Bulls currently contains many of these data classes, but they are distributed across Portal pages, Atlas dossiers, queues, catalysts, strategy experiments, and portfolio views. The primary gap is workflow composition.

## Capability assessment

### 1. Charting and technical analysis

TrendSpider documents automated trendline detection, multi-timeframe overlays, support/resistance heatmaps, hundreds of indicators, pattern recognition, and custom JavaScript studies. Its "Truth in Analysis" behavior exposes the analysis window and allows point-in-time locking for automated trendlines.

Relevant official material:

- [Automated trendline detection](https://help.trendspider.com/kb/automated-technical-analysis/automated-trendline-detection)
- [Multi-timeframe analysis](https://help.trendspider.com/kb/charting/multi-timeframe-analysis)
- [Heatmaps](https://help.trendspider.com/kb/charting/heatmaps)
- [JavaScript custom indicator capabilities](https://trendspider.com/developers/capabilities/)

**Lesson for Bulls:** every computed overlay should display its data cutoff, method version, timeframe, and parameters. Atlas already has stronger point-in-time principles than most retail platforms; that strength should become visible on the chart.

**Do not copy:** proprietary names or visualizations such as Raindrop Charts, their interface, or their exact script ecosystem. Conventional candles, volume profile, anchored levels, event markers, relative strength, and research overlays are sufficient.

### 2. Scanning and smart watchlists

TrendSpider's [Market Scanner](https://help.trendspider.com/kb/scanner/market-scanner) treats a scan as a saved, dynamic condition over a selected universe. It supports technical, fundamental, event, watchlist, current-candle, and multi-timeframe criteria. It can also combine non-technical events with technical rules.

**Lesson for Bulls:** Portal Ideas and Atlas setup families should stop being isolated handwritten endpoints. They should be named, versioned condition definitions with explicit:

- market and universe;
- supported timeframe;
- liquidity and capitalization eligibility;
- condition tree;
- data dependencies;
- freshness policy;
- result explanation;
- current validation status.

This would let a user see exactly why a ticker matched and would make scanner results reproducible.

### 3. Alerts and bots

TrendSpider supports dynamic and multi-factor alerts plus outbound [alert webhooks](https://help.trendspider.com/articles/webhooks). Its [strategy bots](https://help.trendspider.com/kb/trading-bots/trading-bots) lock a strategy version, monitor consistency, and can stop when historical signals move.

The bot documentation also exposes important limitations: stop and target behavior can be candle-close based, a bot is tied to a ticker/timeframe, and forward-looking indicators can invalidate results.

**Lesson for Bulls:** the professional behavior to copy is version locking, dependency health, audit logs, idempotent evaluation, and explicit failure states. Bulls should not add live brokerage execution until paper books, costs, capacity, controls, and operational reconciliation have passed promotion gates.

### 4. Backtesting

TrendSpider's [Strategy Tester documentation](https://help.trendspider.com/kb/strategy-tester/understanding-strategy-tester-from-trendspider) is unusually useful because it states limitations. Defaults may assume perfect execution and zero slippage; capital can be treated as unlimited; options and indices are not directly backtested; long and short are not tested simultaneously in one test; and most tests use a single timeframe unless custom code supplies another.

**Lesson for Bulls:** a visually attractive backtest is not institutional evidence. Atlas should remain stricter:

- point-in-time universe membership;
- corporate-action-aware prices;
- next-observable execution;
- spread, fees, slippage, halts, and partial fills;
- capital and position constraints;
- delisted names where data is available;
- discovery, validation, and untouched holdout periods;
- benchmark and regime attribution;
- immutable run configuration and data fingerprints.

TrendSpider can be used for fast hypothesis rejection and chart verification. Atlas should own certification and capital admission.

### 5. Data breadth and research flows

TrendSpider advertises US equities, options, OTC, futures, indices, crypto, FX, news, fundamentals, analyst estimates, insider data, government trades, Reg SHO, social data, and other alternative feeds. Its [data-flow interface](https://help.trendspider.com/kb/researching-opportunities/data-flow) normalizes several event types into a common timestamped workflow.

Its [data disclaimers](https://trendspider.com/data-disclaimers/) also state that sources differ and additional datasets may be incomplete, erroneous, or delayed.

**Lesson for Bulls:** a common event envelope matters more than adding isolated widgets. Bulls should continue normalizing each event as:

```text
tenant_id / market / instrument_id / event_type
effective_at / known_at / ingested_at
source / source_record_id / revision
materiality / confidence / freshness
raw_evidence_ref / normalized_payload
```

That envelope can drive chart markers, catalyst timelines, alerts, research changes, and outcome analysis without mixing DSE and US evidence.

### 6. Sidekick AI

TrendSpider's [Sidekick documentation](https://help.trendspider.com/kb/sidekick/trendspider-sidekick) describes an AI assistant with tools for platform data, charts, scans, watchlists, fundamentals, filings, options, ownership, short-volume information, government transactions, seasonality, and other datasets. It does not browse the public internet, and real-time data is fetched through tools rather than continuously streamed into the model.

TrendSpider also describes its coding assistant as Anthropic Claude-backed. This does not mean the LLM evaluates every ticker. The scalable pattern is:

1. deterministic data retrieval;
2. structured tool results;
3. explicit active-workspace context;
4. LLM synthesis on request;
5. citations and warnings;
6. metered usage.

**Lesson for Bulls:** Atlas should build a grounded Research Copilot, not a free-form market oracle. The model must never invent prices, fundamentals, catalysts, or trade eligibility. It should call typed tools, cite evidence IDs, disclose missing inputs, and be unable to bypass strategy or risk gates.

## Commercial and integration reality

### Pricing

TrendSpider pricing changes frequently and current pages show promotional terms. As of this study:

- individual plans begin around the price of a professional retail research subscription, with limits increasing by workspaces, alerts, bots, scan frequency, and test universe;
- live professional data and options entitlements may add separate fees;
- Sidekick usage is metered, with additional message packages available;
- [business access](https://trendspider.com/pricing/) is advertised from $399 per month, with team and professional-data terms handled separately.

Pricing must be confirmed at purchase. Bulls should evaluate the product based on analyst-hours saved, not on a temporary promotional price.

### Available integration surfaces

Official documentation supports:

- outbound alert and bot webhooks;
- scripts running within TrendSpider;
- CSV/API upload of user custom series;
- listing and deleting those uploaded custom symbols.

The [custom-data documentation](https://help.trendspider.com/kb/data-feeds/uploading-custom-data-to-trendspider) says uploaded series can be used in charts, strategies, dashboards, and seasonality. It also says timestamps are interpreted in `America/New_York`, uploaded files are limited in size, and the API is not a read API for extracting that data.

Therefore:

- do not treat TrendSpider as Bulls' market-data supplier;
- do not scrape its UI or export licensed data into Bulls;
- do not upload confidential customer data or restricted DSE data without a legal/privacy review;
- do not assume its developer scripting access grants external redistribution rights;
- do not make Atlas availability depend on a third-party retail account.

A safe experiment is owner-only: upload a few non-sensitive Bulls-derived US factor series or import Atlas signal timestamps for visual comparison. This should be a disposable evaluation adapter, not production architecture.

## Bulls current position

### Capabilities already present

Bulls already has meaningful components that should not be rebuilt:

- tenant-bound DSE and US instrument/data domains;
- Portal ticker pages, charts, watchlists, alerts, Ideas, market boards, and pattern research;
- Atlas queues, company dossiers, evidence synthesis, catalysts, hypothesis experiments, portfolio/risk, research memory, and paper books;
- point-in-time architecture using effective, known, and ingestion times;
- deterministic scanner and strategy research jobs;
- model and strategy admission rules;
- market-specific data ingestion, health checks, and provenance;
- PostgreSQL/pgvector for transactional evidence and retrieval;
- Parquet/DuckDB/Polars research paths for larger analytical workloads.

### Important gaps

| Gap | User consequence | Priority |
|---|---|---|
| No universal condition definition | Scanners, patterns, alerts, and tests can disagree | Critical |
| Charts are evidence viewers, not research workspaces | Analysts switch pages and lose context | High |
| Limited scan-to-alert-to-test conversion | Good ideas require engineering work to operationalize | Critical |
| No saved synchronized workspace | Repeated research setup is slow | Medium |
| Explanations are not consistently attached to chart events | Users cannot connect a result to its evidence journey | High |
| AI is not yet a complete grounded workspace operator | Data breadth does not translate into a simple research conversation | Medium |
| US real-time and premium alternative data remain license-gated | Some TrendSpider-like experiences cannot be reproduced legally | Critical gate |
| DSE history and adjusted-price coverage are limited | Long-horizon seasonality and robust strategy validation remain weak | Critical gate |

## Strategic differentiation

### Where TrendSpider is stronger

- mature chart ergonomics;
- breadth of technical tools and licensed US data;
- low-friction condition authoring;
- condition reuse across scan, alert, test, and automation;
- custom scripting and user extensibility;
- polished saved workspaces and multi-panel analysis;
- established operational integrations.

### Where Bulls can be stronger

- native DSE disclosures, ownership, market mechanics, Bangla/English presentation, and local context;
- US small/micro-cap SEC, FINRA, dilution, filing, catalyst, and liquidity evidence;
- explicit tenant and market isolation;
- point-in-time reproducibility and evidence lineage;
- counter-evidence and missing-data states;
- strategy registry, holdout validation, and admission gates;
- portfolio capacity, risk, and measured forward outcomes;
- one research narrative connecting discovery, evidence, decision, and result.

TrendSpider helps an analyst work faster. Bulls should help an investment process remain explainable, reproducible, and accountable.

## First production slice implemented (2026-08-11)

The first Bulls-native slice is intentionally narrower than a charting-platform clone:

- a pure, versioned `research-conditions-v1` analytics registry;
- three completed-daily-session conditions: trend alignment, participation expansion, and
  controlled pullback context;
- backend EMA20 and EMA50 overlays derived by the same analytics module as the explanations;
- point-in-time historical observation transitions using only facts available on each date;
- prior-20-session relative-volume baselines that exclude the evaluated session;
- explicit `observed`, `not_observed`, and `unavailable` states;
- an Atlas company-dossier condition canvas showing every measured input, threshold, limitation,
  and recent observation;
- chart markers for only the selected condition, capped to prevent annotation noise;
- URL-preserved condition, chart mode, and range so an investigation view can be reopened;
- DSE and US reuse the same calculation code while retaining the existing authenticated market
  boundary and separate deployments.

This slice does **not** create an order, paper target, expected-return estimate, strategy
qualification, or alert. Scanner and alert compilation remain a later controlled extension of the
same registry; existing handwritten boards were not silently relabelled as condition-engine output.
That boundary prevents a descriptive chart observation from bypassing Atlas strategy admission and
portfolio risk controls.

## Product architecture recommendation

### A. Bulls Condition Language

Create a safe, typed condition abstract syntax tree rather than accepting arbitrary code from Portal users.

Example concept:

```text
AND
  close > EMA(close, 20)
  EMA(close, 20) > EMA(close, 50)
  slope(EMA(close, 20), 10 sessions) > 0
  relative_volume(20 sessions) >= 1.5
  median_turnover(20 sessions) >= market_policy.minimum
```

Every node must define:

- required fields and history;
- market/timeframe support;
- null behavior;
- point-in-time semantics;
- deterministic implementation version;
- explanation template;
- unit and parameter bounds.

The condition language should compile to four controlled execution targets:

1. SQL/Polars universe scan;
2. chart overlay and event markers;
3. scheduled/incremental alert evaluation;
4. point-in-time backtest and forward paper evaluation.

Do not execute arbitrary user JavaScript in the Bulls backend. A future advanced scripting environment would require strong sandboxing, resource limits, dependency controls, audit logs, and a separate threat model.

### B. Indicator and evidence registry

Each indicator, factor, event, and model output should be registered with:

- stable key and semantic version;
- owner and description;
- market coverage;
- required source datasets;
- supported frequencies;
- calculation code reference;
- freshness and quality thresholds;
- lookahead audit result;
- chart renderer and human explanation;
- deprecation/replacement state.

This stops the UI, scanner, and research jobs from independently reimplementing RSI, relative volume, ownership deltas, or setup states.

### C. Atlas Investigation Workbench

The professional surface should be desktop-first but responsive, with one synchronized context:

```text
+-----------------------------------------------------------------------+
| Symbol | market | timeframe | as-of | layout | data health | actions   |
+------------------+--------------------------------+-------------------+
| Watchlists/scans | Price, volume and overlays      | Evidence tabs     |
|                  | event and decision markers      | filings/news      |
|                  | point-in-time replay            | fundamentals      |
|                  |                                 | ownership/events  |
+------------------+--------------------------------+-------------------+
| Hypothesis | test results | paper book | risk | outcome calibration   |
+-----------------------------------------------------------------------+
| Collapsible grounded Research Copilot with citations and tool log      |
+-----------------------------------------------------------------------+
```

Interaction requirements:

- changing symbol updates every panel;
- changing `as-of` replays only evidence known at that time;
- chart events open the exact source evidence;
- a scan match opens with its condition explanation;
- a condition can be sent to an experiment but cannot become a paper target without admission;
- saved layouts store presentation state, never duplicate market data;
- mobile uses tabs and a focused chart rather than squeezing the terminal into one screen.

### D. Grounded Atlas Copilot

The copilot should operate through typed tools such as:

- `get_price_context`;
- `get_event_timeline`;
- `get_filing_evidence`;
- `compare_fundamentals`;
- `explain_scan_match`;
- `build_condition_draft`;
- `run_diagnostic_backtest`;
- `compare_to_benchmark`;
- `summarize_counter_evidence`;
- `show_portfolio_impact`.

Controls:

- tenant and market are injected server-side, never trusted from model output;
- every factual claim cites evidence IDs;
- structured numeric results come from services, not model arithmetic;
- no tool can place an order or promote a strategy;
- prompt, tools, results, cost, latency, and model version are audited;
- repeated artifacts are cached;
- universe-wide LLM loops are forbidden by policy.

### E. Event stream and chart markers

Filings, earnings, ownership disclosures, senator transactions, FINRA data, DSE disclosures, unusual volume, setup transitions, research decisions, and paper events should share one event API. A chart marker should never be a decorative duplicate. It should link to the normalized event and original source.

## Market-specific design

### DSE

Highest-value near-term features:

1. EOD chart with disclosure, ownership, institutional, dividend, board-meeting, circuit, and Atlas setup markers.
2. Daily/weekly multi-timeframe context where history is sufficient.
3. Saved EOD scans and post-close alerts with a clear next-refresh time.
4. Point-in-time replay connecting setup discovery to later outcome.
5. DSE-native liquidity and market-mechanics gates.
6. Bangla and English explanations generated from the same structured facts.

Do not present unsupported minute-level precision, credible long-horizon seasonality from roughly two years of history, or adjusted-return claims until corporate-action coverage is complete.

### US

Highest-value near-term features:

1. Price/volume chart with SEC filing, earnings, analyst, senator, 13F, FINRA, dilution, catalyst, and setup markers where licensed data exists.
2. Small/micro-cap liquidity, float, dilution, filing-risk, and catalyst overlays.
3. Multi-factor scans combining technical conditions with filing/event evidence.
4. Licensed real-time or delayed alerts with explicit feed status.
5. Strategy tests segmented by capitalization, liquidity, price, regime, and borrowability.
6. Options overlays only after the data license, retention rights, and historical quality are resolved.

Do not infer short interest from FINRA daily short volume, institutional intent from a single 13F change, or real-time edge from delayed/EOD data.

## Build, buy, and avoid

| Decision | Recommendation | Reason |
|---|---|---|
| TrendSpider individual account | **Use for a structured trial** | Immediate US charting and workflow benchmark |
| TrendSpider team/enterprise | **Defer** | Bulls is not yet replacing a multi-analyst desk; verify ROI first |
| TrendSpider as Bulls data API | **Do not use** | No documented general read/redistribution API for this purpose |
| Upload Bulls US factors | **Small owner-only experiment** | Useful for visual validation if data is non-sensitive and licensed |
| Upload DSE/customer data | **Do not do now** | Timezone/session, privacy, and redistribution concerns |
| Import TrendSpider alert webhooks | **Optional experiment** | Can compare third-party signals with Bulls outcomes; never treat as ground truth |
| Bulls condition engine | **Build** | Core reusable infrastructure and strategic moat |
| Atlas Investigation Workbench | **Build** | Converts fragmented data into an analyst workflow |
| Grounded Research Copilot | **Build after typed tools** | AI becomes useful only after deterministic context is reliable |
| Hundreds of indicators | **Avoid** | Breadth without validated use cases increases noise and maintenance |
| Live broker automation | **Avoid now** | Paper evidence, reconciliation, controls, and licensing are not mature enough |
| Proprietary chart imitation | **Avoid** | Legal risk and no strategic advantage |

## Structured TrendSpider evaluation

Before building more, run a 14-day owner evaluation using a fixed scorecard.

### Test set

Use 20 representative symbols:

- 5 liquid US large caps;
- 5 US small caps;
- 5 US micro/penny names with difficult corporate actions or liquidity;
- 5 historical Bulls candidates with known outcomes.

DSE should be assessed in Bulls directly because no documented native DSE coverage was identified during this review.

### Tasks

1. Recreate five existing Bulls conditions.
2. Convert each condition into a scan and alert.
3. Run diagnostic tests with costs and document every assumption.
4. Compare setup timestamps with Atlas point-in-time events.
5. Inspect filing/news/ownership provenance.
6. Ask Sidekick the same ten research questions asked of Atlas.
7. Record incorrect, stale, uncited, or unavailable answers.
8. Measure analyst minutes from ticker selection to a documented conclusion.
9. Export signal timestamps where supported and compare with Atlas outcomes.
10. Record which feature would be cheaper to buy than build.

### Purchase gate

Continue the subscription only if it saves at least five analyst-hours per month or materially improves validation quality. Do not purchase an enterprise plan until at least two active analysts need shared workflows and the commercial data terms have been reviewed.

## Delivery roadmap

### Phase 0: Benchmark and contract

- run the structured TrendSpider trial;
- establish a Bulls chart/scan/alert terminology contract;
- inventory duplicate calculations across Portal and Atlas;
- document US data-display rights and DSE redistribution constraints;
- select ten high-value conditions only.

**Exit:** validated scorecard, calculation inventory, and approved condition schema.

### Phase 1: Research canvas

- add Atlas synchronized symbol, timeframe, and as-of context;
- improve the chart with event, setup, decision, and paper markers;
- add overlay provenance and source navigation;
- add saved workspace layouts;
- add point-in-time replay.

**Exit:** an analyst can investigate one ticker without losing context or opening several disconnected pages.

### Phase 2: Condition engine

- implement the typed condition AST and registry;
- compile to DSE/US EOD scanners;
- compile to chart explanations and markers;
- add scheduled alerts with freshness and data-health gates;
- migrate a small set of existing Portal/Atlas rules.

**Exit:** one versioned condition produces matching chart, scan, and alert results.

### Phase 3: Experiment and paper loop

- compile admitted conditions into point-in-time diagnostics;
- add transaction costs, liquidity, capacity, and benchmark attribution;
- support forward-only paper books;
- surface discovery-to-outcome calibration in Atlas;
- prevent scan results from masquerading as trades.

**Exit:** every paper decision can be traced to a registered strategy, condition version, data cutoff, and risk decision.

### Phase 4: Grounded copilot

- expose typed research tools;
- add evidence citations and tool logs;
- support condition drafting but require deterministic validation;
- cache company research artifacts;
- enforce per-user and per-tenant budgets;
- evaluate factual accuracy and abstention before wider release.

**Exit:** the copilot reduces research time without changing facts, bypassing controls, or triggering universe-wide cost.

### Phase 5: Advanced licensed modules

Only after commercial validation:

- licensed intraday US scanning;
- options/volatility context;
- richer analyst estimates and alternative data;
- advanced custom research scripts in an isolated sandbox;
- broker integration after operational and regulatory review.

## Success measures

### Research productivity

- median time from scan match to documented conclusion;
- percentage of research completed within one synchronized workspace;
- saved-layout reuse;
- evidence-source click-through rate;
- percentage of AI statements carrying valid evidence references.

### Signal quality

- match count and rejection rate by condition version;
- forward 1/5/10/20-session outcome distribution;
- benchmark-relative return and maximum adverse excursion;
- stability by market regime, cap, price, and liquidity tier;
- false alert rate and user dismissal rate;
- capacity-adjusted rather than headline returns.

### Platform quality

- chart/scan/alert parity tests;
- point-in-time leakage tests;
- event freshness SLA by source;
- tenant-boundary and market-boundary tests;
- alert idempotency and duplicate suppression;
- workspace load latency;
- AI cost and latency per completed research task.

## Non-negotiable acceptance rules

1. DSE and US data remain independently scoped by tenant and market.
2. The server derives tenant scope from authenticated context, not client/model parameters.
3. Every chart marker and AI claim links to source evidence.
4. The same condition and data cutoff produce the same result across chart, scanner, alert, and test.
5. No historical rule uses evidence not known at the evaluated time.
6. Missing, stale, or unlicensed data is displayed as unavailable, never silently replaced.
7. A scanner match is research attention, not a recommendation or order.
8. AI cannot promote strategies, size positions, or override portfolio controls.
9. Mobile layouts prioritize one task at a time; desktop may expose synchronized panes.
10. Every newly added feature must improve a measured research workflow, not merely increase widget count.

## Final recommendation

TrendSpider is worth learning from and likely worth a personal trial for Bulls' US research. It should not redirect Bulls into building another generic technical-analysis terminal.

The highest-return Bulls investment is a shared, audited condition engine plus an Atlas Investigation Workbench. That pair would connect the substantial data foundation already built to a simple professional workflow. TrendSpider can shorten the discovery and UX-learning cycle, while Bulls preserves its differentiation in DSE intelligence, US regulatory evidence, point-in-time rigor, portfolio risk, and explainable research outcomes.

## Official sources reviewed

- [TrendSpider pricing and plan limits](https://trendspider.com/pricing/)
- [TrendSpider enterprise solutions](https://trendspider.com/enterprise-solutions/)
- [Market Data Library](https://trendspider.com/marketdata/)
- [Market-data disclaimers](https://trendspider.com/data-disclaimers/)
- [Market Scanner](https://help.trendspider.com/kb/scanner/market-scanner)
- [Strategy Tester limitations](https://help.trendspider.com/kb/strategy-tester/understanding-strategy-tester-from-trendspider)
- [Creating and using strategies](https://help.trendspider.com/kb/strategy-tester/accessing-and-using-the-strategy-tester)
- [Dynamic and multi-factor alerts](https://help.trendspider.com/kb/alerts)
- [Alert and bot webhooks](https://help.trendspider.com/articles/webhooks)
- [Strategy bots](https://help.trendspider.com/kb/trading-bots/trading-bots)
- [TrendSpider Sidekick](https://help.trendspider.com/kb/sidekick/trendspider-sidekick)
- [Automated trendline detection](https://help.trendspider.com/kb/automated-technical-analysis/automated-trendline-detection)
- [Multi-timeframe analysis](https://help.trendspider.com/kb/charting/multi-timeframe-analysis)
- [Seasonality](https://help.trendspider.com/kb/right-sidebar/seasonality)
- [Research data flows](https://help.trendspider.com/kb/researching-opportunities/data-flow)
- [JavaScript custom indicators](https://trendspider.com/developers/capabilities/)
- [Custom-data upload and API behavior](https://help.trendspider.com/kb/data-feeds/uploading-custom-data-to-trendspider)

## Bulls references reviewed

- [`apps/research/README.md`](../../apps/research/README.md)
- [`docs/architecture/institutional-research-os.md`](../architecture/institutional-research-os.md)
- [`docs/research/dse-atlas-readiness-audit-2026-08-03.md`](dse-atlas-readiness-audit-2026-08-03.md)
- [`docs/research/us-market-data-strategy-2026-07.md`](us-market-data-strategy-2026-07.md)
- [`docs/research/bulls-ai-ml-investment-plan-2026-08-04.md`](bulls-ai-ml-investment-plan-2026-08-04.md)
