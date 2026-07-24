# Atlas decision-archive audit, data-readiness matrix, and research program (2026-07-24)

Status: audit of unpushed commit `45280c8` (parent = production `a815e0f`) plus the verified
production data inventory, the strategy opportunity map, the agent-organization design, and the
implementation plan. **Written to be executable by another LLM session**: every claim cites a
file, a table, or a dated production query; every proposed change names its module and its test.

Companion documents (read before coding):
- `docs/research/atlas-investment-mandate.md` — governing mandate (unchanged).
- `docs/research/atlas-model-certification.md` — engine v3 certification and layer gates.
- `docs/architecture/institutional-research-os.md` — system architecture (amended by this audit).
- `docs/research/institutional-study/ledger.md` — verified external-evidence ledger. Check it
  before asserting any number about external funds/anomalies.

---

## A. Executive verdict

Commit `45280c8` is a **well-architected read model with honest intentions and three material
honesty defects**, all now fixed in the working tree on top of the commit:

1. It claimed adjusted-close performance while **DSE has zero adjusted closes in production**
   (verified: `daily_bars` DSE `adjusted_rows = 0`).
2. It claimed per-session capitalization classification while **no capitalization history table
   exists** (`ticker_analytics` is one current row per symbol).
3. Its historical replay claimed "reconstructed point-in-time" while **universe selection,
   liquidity ranking and cap filtering use today's classifications** (`_backtest_universe`
   filters `Symbol.is_active` and today's `TickerAnalytics`).

Additionally, **forward paper promotion was still measured against the survivorship-biased
equal-weight universe baseline** even though backtests now require an explicit independent
benchmark — a policy contradiction, now failed closed. And **forward paper books could fabricate
P&L across corporate actions** (persisted share counts vs. restated adjusted histories) — now
guarded with a deterministic restatement detector that pauses the book.

The tenant/market isolation, append-only event ledger, replay/forward separation, fail-closed
short capability, and 2R-as-risk-geometry framing are genuinely correct and verified by reading
the code and running the tests. Nothing in the commit invents prices, fills or recommendations.

On the research side the verdict is stark and must be stated plainly: **no strategy — DSE or US,
any horizon — currently has promotion-grade data.** DSE fails on corporate-action adjustment and
history depth; US fails on survivorship and historical universe membership; shorts and scalps
fail on wholly absent datasets. Everything runnable is diagnostic. The correct next spend is
data acquisition, not strategy count. This is not a failure of the platform; it is the platform
telling the truth, which is its core product.

**Do not deploy `45280c8` alone.** Deploy it together with the fixes in this working tree
(section K), after the checklist in section M.

---

## B. Critical implementation findings

Ordered by severity. `FIXED` = corrected in this working tree; `OPEN` = deliberate blocker or
follow-up (section L). Line references are to the tree as of this audit.

### B1. CRITICAL — Adjusted-close claim is false for DSE — FIXED
- `services/api/src/api/institutional_research/decision_board.py` — `load_decision_board`
  methodology and `load_decision_candidate_path` `price_basis` asserted
  "split/distribution-adjusted completed closes".
- Production fact (2026-07-24 query): `daily_bars` market=DSE: 194,756 rows, **0 with
  `adjusted_close`**. `adjusted_close()` silently falls back to raw close.
- DSE has frequent bonus/rights issues; a 20% ex-date drop is reported as a -20% "follow-through"
  and can read as a false MAE or false stop distance. This misleads investors — the exact thing
  principle 7/omit-over-mislead forbids.
- Fix shipped: `adjustment_complete()` helper; per-candidate risk note on raw-close paths;
  methodology and price_basis are now computed from the data, not asserted.

### B2. CRITICAL — Capitalization "as known on the archived session" was false — FIXED
- `decision_board.py` queried `TickerAnalytics.as_of_date <= selected_date` with
  `DISTINCT ON (code)`. But `ticker_analytics` has **primary key (market, code)** — one current
  row per symbol, refreshed each EOD (`packages/core/src/bulls/core/models/ticker_analytics.py:23-25`).
  For any archived date older than the current row, every candidate degraded to "unclassified"
  and the tier filter silently emptied; the methodology claimed a per-session classification that
  has never been recorded anywhere.
- Fix shipped: query drops the date filter; methodology states truthfully that the latest known
  classification is used because no historical capitalization archive exists. Building a real
  `cap_tier` history is section L blocker L3.

### B3. CRITICAL — Replay overclaimed point-in-time reconstruction — FIXED (wording), OPEN (data)
- `operator.py::seed_historical_replay` seeds via `execute_backtest` →
  `workflow.py::_backtest_universe`, which selects `Symbol.is_active.is_(True)`, ranks by
  **today's** `last_close * avg_volume_20`, and filters by **today's** `cap_tier`. The replayed
  month therefore contains look-ahead universe selection and survivorship.
- The UI risk note claimed the state was "reconstructed point-in-time from completed historical
  sessions." Only the *execution path* is point-in-time; the *universe* is not.
- Fix shipped: risk note and architecture doc now state exactly which parts are point-in-time
  and which use current classifications. Replay remains excluded from promotion evidence (that
  separation was implemented correctly: `configuration.forward_evidence_started_on`,
  `promotion_evidence_window`, tested in `test_portfolio_evidence_window.py`).

### B4. HIGH — Forward promotion used the survivorship-biased diagnostic benchmark — FIXED
- `advance_shadow_portfolio` compounds `benchmark_nav` as the **equal-weight mean of the current
  observable strategy universe** (`research_strategy.py`, benchmark_returns block). Engine v3
  correctly bans exactly this series from backtest promotion ("cannot support promotion"), yet
  `_evaluate_portfolio_promotion` fed `snapshot.benchmark_nav` into the
  `benchmark_relative_return` gate — the gate that decides real promotion.
- Fix shipped: `evaluate_shadow_promotion(..., benchmark_independent: bool = False)` adds an
  `independent_benchmark` check that **fails closed**; a book can no longer reach "eligible"
  until an explicit independent series (SPY / DSEX) is wired into the forward advance (L2).
  `portfolio.py` records `benchmark_basis` in the promotion config; policy version bumped to
  `atlas-promotion-policy-v2`. Tests updated + new fail-closed test.

### B5. HIGH — Forward books could fabricate paper P&L across corporate actions — FIXED (guard)
- Shadow books persist integer `shares` and `average_cost` in the price scale current at
  snapshot time; every refresh rebuilds bars with **today's** adjustment ratio
  (`workflow.py::_backtest_universe` adjustment block; `portfolio.py::_refresh_shadow_portfolio`
  reuses `latest.positions` verbatim). A split/bonus/revision between refreshes restates the
  scale under the position: a 10:1 split would mark a -90% "loss", trip the deterministic stop,
  and record a false exit — fabricated forward evidence.
- Fix shipped: snapshots now persist `valuation_close` per position;
  `detect_price_scale_restatement()` compares it against the reloaded history before advancing
  and **pauses the book with an explicit refresh_error** on >0.1% mismatch. Legacy snapshots
  without the field are skipped (no false blocks). Tested in `test_decision_board.py`.

### B6. MEDIUM — Displayed stop could diverge from the enforced stop — FIXED
- `decision_board.py` used `RISK_POLICIES[market].position_stop_loss` while each book enforces
  its **pinned mandate** policy (`risk_policy_from_snapshot`). Today the mandate does not
  override the stop, so no user was misled yet; the divergence was latent.
- Fix shipped: `portfolio_stop_loss(portfolio, market)` resolves the pinned mandate first,
  falls back safely. Tested.

### B7. MEDIUM — Closed positions vanish from later archive dates — OPEN (L5)
- `_candidate_codes` derives candidates from the selected snapshot's positions/targets/events
  only. A position closed last week does not appear on today's board, weakening "what changed"
  and post-exit accountability. Follow-up: derive a closed-book section from historical events
  within a trailing window.

### B8. MEDIUM — US analytics/benchmark staleness — OPEN (ops)
- Production: `market_summary` US ends 2026-07-20 while US bars end 2026-07-23 (also flagged as
  the one critical issue in `atlas-model-certification.md`). Dossier benchmark overlays and any
  freshness-sensitive display lose the last three sessions. Operational fix before deploy.

### B9. LOW — Assorted
- `decision_board.py::load_decision_candidate_path` re-runs the whole board to find one
  candidate — O(portfolios × events) per chart click; fine at n=2 books, revisit at n≳20 (L6).
- `sessions_since_discovery = len(path_prices)` counts the discovery session itself (reads "1"
  on day zero).
- `DecisionPathChart.tsx::marker` labels every non-exit signal "Discovered", including later
  re-qualifications.
- `decision-ticket.ts` mixes the live `currentPrice` with the snapshot-date NAV for
  `currentWeightPct` (approximation, labeled loosely).
- Production `insider_transactions` still contains 32 rows with impossible
  `transaction_date` (< 1990 or > 2026) predating commit `82cdd8e`'s ingestion guard —
  backfill-clean or filter at query time in the backtests.
- `available_dates` capped at 260 snapshots; an `as_of` older than the cap returns the empty
  state (acceptable; document).

### What was verified clean (attempted invalidation failed)
- **Tenant isolation**: every research query filters workspace + organization + tenant + market;
  RLS context bound per request (`bind_research_tenant_context`); FK constraints carry the
  four-column scope; the frontend re-asserts the boundary (`assertDecisionBoardBoundary`).
  Cross-market strategy seeding is refused (`operator.py`, tested).
- **Next-session execution**: targets decided at T fill no earlier than T+1 at open/close plus
  half-spread and fees; certification known-answer tests pass
  (`scripts/certify_atlas_engine.py`, engine v3 sell-before-buy fix verified).
- **Replay/forward separation** in promotion evidence (B3 data caveat aside) is correct and
  tested.
- **Short capability fails closed** on both markets with accurate reasons; FINRA daily short
  volume is explicitly named as a non-substitute.
- **2R objective** is computed as risk geometry from the stop basis and labeled "not a
  forecast" everywhere it appears.
- **Events ledger**: append-only, idempotent keys, hash-checked payloads, causal links
  (`investment.py::record_snapshot_decision_events`).

---

## C. Data-readiness matrix (verified against production, 2026-07-24)

All numbers from read-only queries on the production Postgres this session, not from docs.

| Dataset | Source | Market | Range | Latest | Coverage | Freq | Point-in-time | Survivorship | Corp-action | Known limitations | Usable by |
|---|---|---|---|---|---|---|---|---|---|---|---|
| EOD bars DSE | dsebd scraper | DSE | 2024-06-27 → | 2026-07-23 | 401 codes (396 active), 194,756 rows | daily | ingestion-time (`daily_bar_observations` lineage 100%) | **no delisted rows** | **NONE — 0 adjusted closes** | 492 sessions ≈ 2.07y; raw closes only | diagnostics only |
| EOD bars US | free EOD adapter | US | 2016-07-11 → | 2026-07-23 | 11,072 codes, 16.49M rows | daily | lineage 100% | **~50 inactive of 11,129 — survivors-only** | adjusted_close on 16.49M rows (retroactive restatement on new events) | delisted histories absent; adjustment audit not done | diagnostics; large-cap sleeves least-biased |
| SPY benchmark | same | US | 2016-07-11 → | 2026-07-23 | 2,523 rows | daily | n/a | n/a | adjusted (TR proxy) | ETF, not the cash index — labeled | backtest benchmark ✅ |
| DSEX index | `market_summary.dsex` | DSE | 2024-06-27 → | 2026-07-23 | 492 rows | daily | n/a | n/a | price index (ex-dividend) | 2 years only; price-only index vs raw-close books — roughly consistent basis | backtest benchmark ✅ (short) |
| Intraday DSE | delayed poller | DSE | **2026-07-20 →** | 2026-07-23 | 396 codes, 26,573 rows (4 sessions) | ~15-min slots | capture-time | n/a | n/a | four sessions | nothing |
| Intraday US | — | US | **none** | — | — | — | — | — | — | does not exist | nothing |
| Delayed quotes | poller | both | rolling | 2026-07-23 | DSE 396 / US 10,966 | intraday | capture-time | n/a | n/a | display freshness only | UI only |
| Security master | EDGAR/registry | US | current | 2026-07-22 | 13,093 rows, 9 instrument types, 5,871 common/ADR | refresh | **current-state only** | — | — | `security_listing_observations` PIT capture began **2026-07-17** (one observation) | instrument-type filter ✅; membership history ❌ |
| Security master DSE | scraper | DSE | current | — | 396 rows, 1 type | refresh | current-state only | no delistings recorded | — | same | — |
| Market-cap / tier | `ticker_analytics` | both | **current row only** | 2026-07-23 | DSE 395/396 tiered; US 4,162/11,072 | daily overwrite | **none — no history** | — | — | cannot reconstruct any historical tier | current filtering only |
| Fundamentals US | SEC Company Facts | US | 2018-07-19 → (`known_at`) | 2026-07-23 | 4.22M obs, 5,188 codes | filing-driven | **real PIT via `known_at`** ✅ | tied to price-store survivorship | n/a | pre-2018 known_at absent | System C inputs, quality screens |
| Fundamentals DSE | weekly company scrape | DSE | ~5 periods/company | current | 1,969 rows, 395 codes | weekly scrape | `known_at` = ingestion upper bound | — | — | shallow history; publication time unknown | descriptive only |
| DSE disclosures | dsebd announcements | DSE | 2024-07-02 → | 2026-07-23 | 16,650 rows, 697 codes | daily | published_at | includes non-active codes ✅ | n/a | 2 years; materiality policy now in `disclosure_materiality.py` | catalysts, evidence |
| DSE ownership | monthly shareholding | DSE | 2016-06-30 → | 2026-06-30 | 1,567 rows, 395 codes | monthly snapshots | snapshot dates | — | n/a | **sparse** (~4 rows/code average — coverage uneven; verify per-code before use) | sponsor/institute deltas (descriptive) |
| EDGAR filings | EDGAR | US | 2010-06-21 → | 2026-07-22 | 1.05M events, 51,410 CIKs | accepted_at | **real PIT** ✅ | issuer-complete | n/a | — | event timing ✅ |
| Form 4 | EDGAR | US | 2003→ effective | 2026-07-22 | 1.72M rows, 7,852 issuers | accepted_at | **real PIT** ✅ | issuer-complete; price outcomes survivor-biased | n/a | 32 impossible-date rows remain (pre-`82cdd8e`) | System A ✅ (with price caveat) |
| 13D/13G | EDGAR | US | 2021-06-30 → | 2026-07-22 | 153,616 events, 9,591 subjects | accepted_at | **real PIT** ✅ | — | n/a | 5 years; post-2024 5-bd deadline regime | activist follower ✅ (thin) |
| 13F | EDGAR | US | **2024-06-30 →** | 2026-03-31 | 636,631 positions, 8,385 managers | quarterly, 45-day lag | filing-time | — | n/a | **8 quarters**; no shorts/swaps ever; **never call it live flow** | nothing yet |
| FINRA short volume | FINRA daily files | US | **2026-06-08 →** | 2026-07-23 | 336,869 rows, 11,110 codes | daily | file date | — | n/a | **6.5 weeks**; short-marked volume ≠ short interest ≠ borrow | descriptive dossier only |
| Catalysts | derived table | both | Jul 2026 → | current | DSE confirmed events; US inferred windows | daily crons | derivation-time | — | n/a | weeks old; US windows are inferred, never confirmed | forward collection only |
| News/knowledge | announcements + chunks | both | as above | current | 5.6GB chunks | — | — | — | — | RAG evidence, not signals | evidence |
| Options | — | US | **none** | — | — | — | — | — | — | Cboe DataShop evaluation pending (owner to obtain quote) | nothing |
| Borrow/locate | — | US | **none** | — | — | — | — | — | — | hard blocker for any short | nothing |
| Liquidity/spread | `cost_observatory` estimates | both | derived | current | measured half-spreads + tiers | daily | estimate-time | — | — | estimates, not prints; stress tiers 10/30/50bps exist | cost gates ✅ |

**Language discipline (hard rules, verified into UI copy):** FINRA daily short volume is never
"short interest"; 13F/ownership changes are never "live flow"; a reconstructed replay is never
"forward paper evidence"; missing data renders as unavailable, never zero.

---

## D. Strategy opportunity map

Machine-readable source of truth: `packages/analytics/src/bulls/analytics/strategy_readiness.py`
(new this session; tests in `packages/analytics/tests/test_strategy_readiness.py`). Statuses:
`backtest_ready` / `diagnostic_only` / `blocked`. **Current count: 0 ready, 10 diagnostic, 6
blocked.** The catalog is the only place the API/UI may read blocked-reasons from.

Full per-strategy specification (hypothesis, market, tiers, holding period, PIT inputs, signal
formula, entry, fill timing, sizing, invalidation, stop, exit, target methodology, liquidity
constraints, costs, benchmark, capacity, regime filters, failure modes, missing data, status):

| # | Strategy | Mkt | Status | Core spec |
|---|---|---|---|---|
| 1 | `dse_reversal_v1` liquid mean reversion (implemented) | DSE | diagnostic | Signal: z-score of 5-session return < -2 within top-liquidity names; entry next open; stop = policy `position_stop_loss` from avg cost; exit on reversion target-weight removal or stop; costs = measured half-spread + fees; benchmark DSEX; blocked from promotion by raw closes + 492 sessions |
| 2 | DSE trend continuation / micro-pullback | DSE | diagnostic | Hypothesis: under-reaction continuation after controlled pullback (owner's preferred, evidence-gated). Inputs: adjusted bars (missing), 50/200 SMA, pullback depth < 1×ATR, rel-volume confirmation; entry on pullback stabilization next open; stop below pullback low; 2R risk geometry objective; needs DSE adjustments + depth |
| 3 | DSE sponsor/insider accumulation | DSE | diagnostic | DSE-unique edge candidate: insider-category disclosures + sponsor% deltas; entry on cluster of sponsor buys; needs sparse-ownership verification per code; descriptive until adjustments land |
| 4 | DSE scalping | DSE | **blocked** | 4 sessions of intraday data; refuse |
| 5 | `us_breakout_v1` VCP/flat-base breakout (implemented) | US | diagnostic | Range compression (ATR contraction + base length) with volume confirmation; next-open fill; survivorship inflates results — diagnostic until delisted history exists |
| 6 | Post-breakout retest | US | diagnostic (same inputs as 5) | Variant entry rule of 5; do not register as a separate paper book (would double-count the same factor) |
| 7 | US large-cap liquid mean reversion | US | diagnostic → **nearest to ready** | Restrict to mega/large caps continuously listed 2016→now (survivorship error smallest and boundable); 3-5 session reversion z-score; next-open fill; explicit SPY benchmark; quantify the residual bias before any promotion claim |
| 8 | Oversold-quality reversal | US | diagnostic | Quality screen from PIT Company Facts (2018→) + drawdown entry; position horizon; same survivorship caveat |
| 9 | Accumulation/participation confirmation (OBV/CMF) | both | diagnostic | Only as a confirmation overlay for 2/5 — not a standalone book (same underlying factor) |
| 10 | Earnings/disclosure drift | US | diagnostic | Small-cap-only per Martineau 2022 (ledger row); PIT `known_at` facts; costs decide; must pass cost-tier stress before anything |
| 11 | `us_insider_cluster_v1` System A (implemented) | US | diagnostic | Opportunistic-cluster detection at accepted_at dissemination; next-close fills; event-timing +21-session placebo already implemented; forward book IS the modern re-test (ledger row 107) |
| 12 | `us_activist_13d_v1` System A' (implemented) | US | diagnostic | Preregistered activist roster (allow-list IS the strategy); 2021→ events only; thin sample — keep collecting |
| 13 | 13F institutional-ownership change | US | **blocked** | 8 quarters + 45-day lag = no sample; revisit ≥ 2029 or buy history |
| 14 | `us_forced_seller_v1` System B (implemented, parked) | US | **blocked** | Preregistered spin-off/deletion/liquidation event datasets not built; year-2 drift concentration per Cusatis-Miles-Woolridge (ledger row 105) |
| 15 | `us_factor_sleeve_v1` System C VQM (implemented) | US | diagnostic | Monthly rebalance, 4 PIT factors, next-close; French momentum reproduction control blocked on historical market equity + membership; equal-weight/eligible-universe nulls implemented |
| 16 | Catalyst continuation | both | diagnostic | Catalyst archive weeks old; collect forward outcomes ≥ 2 quarters first |
| 17 | Long/short relative value | US | **blocked** | Short leg impossible (borrow); do not model as long-only tilt (different strategy) |
| 18 | Short breakdown / failed breakout | US | **blocked** | Research allowed, paper execution fail-closed until borrow/locate/fee/recall/squeeze datasets exist — implemented in `direction_capabilities` |
| 19 | US scalping | US | **blocked** | No intraday data at all |
| 20 | Options-signal strategies | US | **blocked** | No options data; Cboe evaluation pending |

Common execution/costs across all: engine v3 (`research_strategy.py`) — next-session fills only,
half-spread + fee costs, ADV participation caps, position stops from average cost, sector/gross
limits, drawdown ladder with operator-cleared freeze, cost-tier stress at 10/30/50bps.

---

## E. Strategies rejected and why

- **Aggregate 13D-follower (all filers)** — rejected: the aggregate tape carries no reliable
  edge (roster selection IS the strategy; already encoded as an allow-list in System A).
- **Aggregate 13F cloning** — rejected: Griffin–Xu shows aggregate HF holdings uninformed;
  conditional cloning would need manager-concentration history we lack (8 quarters).
- **Quarter-end window-dressing predictability** — rejected: the peer-reviewed literature
  directly disagrees with itself (ledger row 63); the study forbids leaning on it.
- **PEAD in mid/large caps** — rejected: documented dead post-2006 outside microcaps
  (ledger row 36); only the small-cap variant remains a diagnostic candidate.
- **Any DSE backtest presented as promotion evidence** — rejected on two independent grounds
  (adjustments, depth); no parameterization can rescue it.
- **Short-side anything with FINRA daily volume as a borrow proxy** — rejected; the file
  measures short-marked volume, not borrow availability or cost.
- **Separate books for breakout + retest + accumulation confirmation** — rejected as factor
  duplication; one compression/participation book, variants as entry rules only.
- **Intraday/scalp families** — rejected until years, not sessions, of intraday history exist.
- **A DSE "momentum because it worked in the US" transplant** — rejected: no local evidence,
  no adjusted data, and DSE market structure (floor prices, circuit breakers, retail dominance)
  invalidates the imported priors. Test locally when data permits.

---

## F. Proposed agent organization

Principle (already enforced by the codebase and preserved): **LLMs narrate; deterministic code
decides.** Prices, signals, eligibility, fills, sizing, stops, limits, P&L, and promotion live
in persisted evidence and deterministic modules. LLM output is display-layer only and must cite
persisted rows.

Bounded agents, mapped to modules (build order in §J):

| Agent | Kind | Reads (typed) | Writes (typed) | Existing module |
|---|---|---|---|---|
| Market Regime | deterministic | `DailyBar`, `MarketSummary` | `RegimeState{market, trend, breadth, vol_bucket, as_of}` | partial (`robustness_slices`); new `analytics/regime.py` |
| Trend/Pullback Scout | deterministic | adjusted bars, `TickerAnalytics` | `SignalCandidate` | `research_strategy` strategies |
| Breakout/Compression Scout | deterministic | same | `SignalCandidate` | `us_breakout_v1` |
| Mean-Reversion Scout | deterministic | same | `SignalCandidate` | `dse_reversal_v1` (+US large-cap variant) |
| Fundamental Quality | deterministic | `SecFinancialFactObservation` (known_at ≤ cutoff) | `QualityScore{inputs, formula_version}` | `factor_sleeve` |
| Filing & Catalyst | deterministic + LLM extraction | EDGAR events, announcements, `research_catalyst_events` | `CatalystEvent` (typed, sourced) | `catalysts.py`, `disclosure_materiality.py` |
| Insider/Ownership | deterministic | Form 4 (accepted_at), 13D/G, shareholding | `OwnershipEvent` | `filing_signals.py` |
| Short Research | deterministic, **execution fail-closed** | short-volume (descriptive), price structure | `ShortResearchNote{blocked_reason}` | `direction_capabilities` |
| Evidence Verifier | deterministic | claims vs. persisted rows | `EvidenceRequirement{present, as_of}` | `evidence.py` bundles |
| Skeptic/Thesis-Break | deterministic + LLM comparison | counter-evidence queries | `ThesisBreak{trigger, source}` | `_thesis_breaks` in backtests; generalize |
| Liquidity & Execution | deterministic | `cost_observatory` | `ExecutionPlan{half_spread_bps, adv_cap}` | exists |
| Portfolio Construction | deterministic | targets + mandate | `constrain_target_weights` output | exists |
| Independent Risk | deterministic | positions, NAV path | `RiskIntervention`, drawdown-ladder actions | exists |
| Paper Execution | deterministic | pending targets + next bars | `BacktestTrade`, decision events | `advance_shadow_portfolio` |
| Outcome & Calibration | deterministic | `ResearchOutcomeObservation`, snapshots | promotion evidence, MFE/MAE | `promotion_evidence_window`, outcome tables |
| Narrator (only LLM-fronted surface) | LLM | all of the above, read-only | display stories citing event keys | dossier/decision-board stories (currently template strings — keep) |

Anti-duplication rule (enforced in the readiness catalog): agents #2/#3 variants and volume
confirmation are one factor family — one paper book, several entry rules; never three books.

Typed contract rule: every inter-agent payload is a Pydantic model persisted before the next
agent reads it; no agent may pass another agent free text as an input. LLM extraction outputs
(e.g., catalyst details) must land in typed columns with source references before use.

---

## G. Typed system architecture (as-built + amendments)

Already correct in the codebase (verified):
- `ResearchWorkspace` → `ResearchShadowPortfolio` → `ResearchShadowSnapshot` (immutable daily) →
  `ResearchDecisionEvent` (append-only causal ledger, idempotent keys, payload hashes) — all
  four-column tenant/org/market scoped with composite FKs.
- `BacktestResult` now carries `benchmark_key/label/method/coverage_pct/valid`.
- `DecisionBoardOut` / `DecisionCandidateOut` / `DecisionCandidatePathOut` (schemas.py) — the
  read contract for the Today page, market-agnostic, no `if market == US` scattering (market
  differences live in `MarketProfile`, `RISK_POLICIES`, and tenant config — verified).
- New: `StrategyReadiness` catalog (section D) as the single blocked-reason source.

Amendments this session: `evaluate_shadow_promotion(benchmark_independent)`,
`portfolio_stop_loss`, `adjustment_complete`, `detect_price_scale_restatement`,
`valuation_close` persisted per position.

To add (section J): `RegimeState`, `SignalCandidate`, cap-tier history table
(`ticker_analytics_history` or `cap_tier_observations`), benchmark series in shadow advance.

---

## H. Backtest and paper-trading framework

Implemented and verified in engine v3 (`research_strategy.py`, `workflow.py`):
1. Next-session execution; sells funded before buys; ADV caps; cash limits.
2. Cost realism: measured per-name half-spreads + fee, stress tiers 10/30/50bps
   (`run_cost_tiered_backtest`); `edge_survives` now requires a valid explicit benchmark.
3. Hard gates: ≥756 sessions, ≥20 securities, ≥30 executions, PIT-completeness flag, explicit
   independent benchmark ≥98% coverage incl. boundaries, deflated-Sharpe gate
   (`_deflated_sharpe_gate`), null comparators (equal-weight universe, eligible-universe,
   event-timing +21-session placebo), drawdown-ladder freeze honesty.
4. Regime slices: five named windows (`robustness_slices`).
5. Shadow promotion: ≥60 forward sessions, ≥10 forward executions, excess ≥2%, max DD ≤15%,
   source historical validation, **and now an independent benchmark basis** — replay excluded
   via `promotion_evidence_window`.

Missing (specify before any promotion claim; J-priorities):
- **Untouched holdout**: reserve the most recent 12 months of any future full-history dataset;
  never run discovery on it; one-shot evaluation with preregistered spec hash (the
  `_stable_hash` idempotency machinery already exists for this).
- **Walk-forward**: rolling 3y-train/1y-test folds; report fold dispersion, not the best fold.
- **Parameter sensitivity**: ±25% perturbation of every threshold; reject if sign flips.
- **Cap-tier robustness**: per-tier result decomposition (needs tier history — L3).
- **Turnover/capacity**: annualized turnover and NAV at which ADV caps bind (partially present
  via `cumulative_turnover` + `adv_capacity` interventions; surface as explicit metrics).
- **Outlier dependence**: re-run excluding top-2 winners; reject if the edge disappears.
- **Certification precondition**: `certify_data_foundation` attestations must reference a real
  dataset manifest before any `backtest_ready` flip in the readiness catalog.

---

## I. Atlas UX specification (Today page)

The eleven questions, mapped to surfaces (most already exist in `DecisionBoardPanel`):
1. *What's new?* — `is_new` flag + "New" chip (exists). Add a "since yesterday" diff strip
   (targets formed / filled / blocked / exited counts vs. prior snapshot).
2. *Actionable next session?* — "Entries" filter (`ready` + `blocked`) (exists).
3. *Needs management/exit?* — "Positions"/"Exits" filters (exists).
4. *Blocked and why?* — rejection risk notes per candidate (exists) **plus** the strategy-level
   blocked registry from `strategy_readiness.py` (new panel: "What Atlas refuses to trade and
   why", listing blocked strategies with their missing datasets).
5. *What changed?* — B7 follow-up: trailing closed-position section + event diff.
6. *Replay vs forward?* — `evidence_mode` chip + corrected honest replay note (fixed).
7. *How has each discovery performed?* — discovery price/date, return, MFE/MAE, sessions
   (exists; "not paper P&L" label verified).
8. *Evidence for/against?* — link into dossier evidence bundles (exists via "Open company
   research"); surface the top thesis-break inline later.
9. *What invalidates?* — invalidation price from the enforced stop (fixed to pinned mandate).
10. *Holding horizon?* — per-strategy horizon text (exists; move `_STRATEGY_HORIZONS` into
    `StrategyDefinition` to keep registry-driven — J item).
11. *Paper portfolio performance?* — NAV/benchmark/drawdown from snapshots (exists in command
    page); label the benchmark as the diagnostic universe baseline until L2 lands.

Rules kept: no unexplained composite score anywhere; plain-language story + expandable
calculation basis; every price labeled with its basis (adjusted vs raw — now truthful);
delayed data marked; no buy/sell language.

---

## J. Prioritized implementation plan (for the next coding session)

P0 (before deploying this branch): section M checklist; nothing else.

P1 — truth infrastructure (unblocks everything):
1. **DSE corporate-action adjustment factors**: reconcile the Mendeley DSE dataset
   `23553sm4tn` (CC BY 4.0, Oct 2012–Jan 2026, adjusted + availability metadata — see memory
   note and `us-market-data-strategy-2026-07.md`); build `dse_adjustment_factors` table +
   backfill `adjusted_close`; acceptance: `adjustment_complete()` true for DSE, decision board
   methodology flips automatically (it is data-driven now).
2. **Explicit benchmark in the forward advance**: pass a `BenchmarkSeries` (SPY/DSEX) into
   `advance_shadow_portfolio`; persist `benchmark_basis` on snapshots; flip
   `benchmark_independent=True` in `_evaluate_portfolio_promotion` only when the series is
   present for the full window. Tests: promotion flips only with the explicit series.
3. **Cap-tier history**: nightly append `(market, code, as_of_date, cap_tier, market_cap_mn)`
   to a new `cap_tier_observations` table (write in `refresh_analytics`); decision board reads
   the row ≤ selected_date when available, falls back to current with the existing honest
   methodology sentence. Migration + backfill from today forward only (no invented history).
4. **US delisted history acquisition decision** (owner): vendor evaluation (e.g., survivorship-
   complete EOD source) — until then the readiness catalog stays diagnostic-only, enforced by
   `test_no_strategy_is_backtest_ready_on_current_data`.

P2 — evidence collection (cheap, time-based value):
5. Keep `security_listing_observations` and catalyst crons running (PIT history accrues daily).
6. Backfill-clean the 32 impossible Form 4 dates; add a range predicate in System A loaders.
7. Fix US `market_summary`/analytics staleness ops issue (watchdog check for post-EOD analytics
   date == bars date).
8. Wire `strategy_readiness.py` to an API endpoint + "blocked strategies" panel (UX §I.4).
9. B7 closed-position trailing section; move `_STRATEGY_HORIZONS` into `StrategyDefinition`.

P3 — validation depth (needs P1 data):
10. Walk-forward + holdout + sensitivity harness per §H, as `workflow.py` additions with
    preregistered spec hashes.
11. French momentum reproduction once historical market equity + membership exist
    (`factor_reproduction.py` is ready and tested; it needs inputs, not code).
12. Rerun Systems A and C under engine v3 with explicit SPY benchmark; invalidate stored
    engine-v2 verdicts (cert doc requirement).

Never: auto-deploy; auto-flip readiness statuses; LLM-computed numbers.

---

## K. Code and tests completed (this session, on top of `45280c8`)

| Change | Files | Tests |
|---|---|---|
| Promotion fails closed on diagnostic benchmark basis | `research_strategy.py` (`evaluate_shadow_promotion` + new check), `portfolio.py` (caller, policy v2, `benchmark_basis`) | `test_research_strategy.py` (updated + new fail-closed test) |
| Corporate-action restatement guard for forward books | `portfolio.py` (`detect_price_scale_restatement`, `valuation_close` persisted, pause-on-restatement) | `test_decision_board.py::test_price_scale_restatement_guard...` |
| Truthful price basis (DSE raw closes) | `decision_board.py` (`adjustment_complete`, dynamic methodology + price_basis + per-candidate risk note) | `test_decision_board.py::test_adjustment_completeness...` |
| Truthful capitalization basis + unbroken archive filtering | `decision_board.py` (query + methodology) | covered by board tests; behavior change documented |
| Honest replay labeling | `decision_board.py` risk note; `institutional-research-os.md` | — (copy) |
| Stop from pinned mandate | `decision_board.py` (`portfolio_stop_loss`) | `test_decision_board.py::test_portfolio_stop_loss...` |
| Strategy readiness catalog (blocked strategies registered with missing data) | `strategy_readiness.py` (new) | `test_strategy_readiness.py` (new, 6 tests) |
| Docs corrected | `institutional-research-os.md`; this document | — |
| Explicit forward benchmark (SPY/DSEX) in the shadow advance | `research_strategy.py` (`advance_shadow_portfolio(benchmark_return=…)`), `portfolio.py` (series load, per-session compounding, `benchmark_explicit_since`) | `test_research_strategy.py`, `test_portfolio_evidence_window.py` (mixed windows fail closed) |
| Cap-tier history recording | `ticker_analytics.py` (`CapTierObservation`), migration `b3d5f7a9c1e3`, `ingestion/analytics.py` writer, `decision_board.py` reader with honest fallback | full suite |
| Squeeze Research module | see `docs/research/squeeze-research-2026-07-24.md` §K | 11 engine tests + API contract tests + preview verification |
| Registry-driven horizons | `StrategyDefinition.horizon/expected_holding`; `_STRATEGY_HORIZONS` dict deleted | full suite |
| Form 4 impossible-date guards | `system_a_backtest.py`, `institutional_backtests.py` | full suite |

Verification: `uv run pytest packages/analytics services/api` → **515 passed** before catalog,
**521 passed** after; `ruff check` and `ruff format` clean on touched files; frontend vitest
(decision-ticket, decision-board) 7 passed; no schema migration required (JSONB additions are
backward-compatible; `valuation_close` is additive and legacy snapshots are tolerated).

---

## L. Remaining blockers

| # | Blocker | Owner action |
|---|---|---|
| L1 | US delisted/acquired price histories + historical universe membership | vendor decision (owner); until then every US backtest stays diagnostic |
| L2 | Explicit benchmark series in the forward shadow advance | next coding session (J.2) |
| L3 | Capitalization-tier history table | next coding session (J.3), accrues from first deploy |
| L4 | DSE adjustment factors (Mendeley reconciliation) + DSE depth (2012→ backfill) | data task (J.1); owner licensing check on redistribution |
| L5 | Closed-position visibility on later archive dates | J.9 |
| L6 | `load_decision_candidate_path` scalability at many books | revisit at n≳20 books |
| L7 | Borrow/locate/fee dataset for any short work | owner licensing; capability stays fail-closed |
| L8 | Options dataset (Cboe quote) | owner |
| L9 | US analytics/market_summary staleness (ops) | J.7 before or right after deploy |
| L10 | 32 impossible Form 4 dates in prod table | J.6 cleanup |
| L11 | Sparse DSE shareholding history (~4 rows/code avg) — verify per-code coverage before any ownership-based strategy | data audit task |

---

## M. Production deployment checklist (do not run without the owner's go)

Constraints: **never deploy during the DSE session or 13:00–13:50 UTC EOD window** (CLAUDE.md);
today is Friday — DSE closed, US open; prefer after 20:00 UTC or the weekend.

1. Pre-flight (local):
   ```bash
   uv run ruff check . && uv run ruff format --check .
   uv run pytest
   .venv/bin/python scripts/certify_atlas_engine.py
   cd apps/research && npx vitest run && npm run build
   ```
2. Commit the audit fixes as a separate commit on `release/atlas-release-a-zero-ltp-fix`
   (message: `fix(research): audit corrections — honest price/cap basis, fail-closed promotion benchmark, corporate-action guard`),
   keeping `45280c8` intact for review lineage.
3. Backend deploy (no migration in this branch — verify: `git diff a815e0f..HEAD -- '*alembic*'`
   is empty):
   ```bash
   DEPLOY_SSH_HOST=bullstreetai ./deploy.sh
   ```
4. Post-deploy backend verification:
   ```bash
   ssh bullstreetai 'systemctl status bullsofdhaka-api bullsofdhaka-worker bullsofdhaka-ai-worker --no-pager | head -30'
   curl -s https://api.bullsofdhaka.com/health
   ```
   Then hit `/institutional-research/workspaces/<id>/decision-board` for one DSE and one US
   workspace; confirm (a) DSE methodology says raw closes + corporate-action warnings present,
   (b) archived dates keep their cap tiers, (c) replay note carries the current-classification
   caveat, (d) promotion config shows `benchmark_basis` + `atlas-promotion-policy-v2`.
5. Research frontend deploy (both tenants):
   ```bash
   ATLAS_AWS_PROFILE=bulls-deployer <atlas web deploy per tenant — bucket bulls-atlas-<tenant>-982534375924, CF E24SO1RMZPETA8 / E3CN2548II8XWY>
   ```
6. Watchdog check next EOD: worker cron ran, snapshots advanced by exactly one session per
   active book, no book paused with `refresh_error` (if one paused on the restatement guard,
   that is the guard working — investigate the corporate action before clearing).
7. Rollback: backend `git revert` + `./deploy.sh`; no data rollback needed (all changes are
   additive JSONB/labels).

---

*Prepared by the 2026-07-24 audit session. The working tree contains the fixes; commit `45280c8`
alone does not.*
