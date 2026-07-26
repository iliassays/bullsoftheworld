# Atlas Squeeze Research module — audit, taxonomy, and implementation contract (2026-07-24)

Status: governing document for the Squeeze Research module. Written so another LLM session can
pick up any blocked family the day its dataset lands. Read together with
`docs/research/atlas-decision-archive-audit-2026-07-24.md` (the same-day platform audit whose
production inventory this document reuses) and `docs/research/atlas-investment-mandate.md`.

The objective is not exciting alerts. It is to identify early, tradeable, measurable squeeze
conditions, reject late or weak setups, simulate execution realistically, and establish through
forward evidence whether any squeeze strategy has durable value. The module must be able to say
"too late" and "we cannot know" — those answers are products, not failures.

---

## A. Implementation audit (what existed before this module)

- `us_breakout_v1` (registered strategy + paper book) already implements a
  compression/participation breakout ranking. The squeeze module's compression-breakout family
  **reuses that logic family rather than duplicating it**: the monitor detects and archives the
  setup taxonomy; the existing registered book remains the only paper-execution surface for it.
- The decision archive (`decision_board.py`) already provides immutable snapshots, causal
  events, discovery tracking, MFE/MAE and replay/forward separation for *paper books*. The
  squeeze monitor mirrors that pattern for *setup taxonomy states* with its own append-only
  table (`squeeze_daily_states`) because setups exist before (and without) any book.
- A first-draft "squeeze watch" (short-marked-volume ranking) was superseded by this design:
  ranking on FINRA daily short-marked share alone was rejected because that series cannot
  establish positioning and would have manufactured a misleading list.
- No existing Atlas surface uses the words "short squeeze"; the phrase enters the codebase only
  behind the data gates defined here.

## B. Squeeze data-readiness matrix (verified against production 2026-07-24)

| Dataset | Status in Atlas | Detail |
|---|---|---|
| EOD OHLCV | ✅ | US 2016-07→ (survivors-only, adjusted); DSE 2024-06→ (raw closes, **no adjustments**) |
| Intraday bars | ❌ effectively | DSE began 2026-07-20 (4 sessions); US none |
| Free float | ✅ DSE only | DSE 359/396 (`free_float_cap_mn`); **US 0/11,072** |
| Shares outstanding | ✅ US (PIT) | 254,581 SEC `shares_outstanding` observations with `known_at`; NOT a float substitute |
| Market capitalization | partial | US 4,171/11,072; DSE 395/396; history collection began 2026-07-24 (`cap_tier_observations`) |
| Short interest | ✅ **2026-07-25** | FINRA consolidated short interest, `short_interest_biweekly`. History to 2020, ~22k symbols per settlement date. Gated on `known_at` = settlement + 8 trading days, never on settlement date |
| FINRA daily short-marked volume | ✅ short history | 2026-06-08 → present, 11,110 codes. **Not short interest; includes market-maker liquidity provision; cannot establish open positions or days-to-cover** |
| Days to cover | ✅ **2026-07-25** | Published by FINRA per settlement date and recorded verbatim, not recomputed (FINRA uses its own volume window) |
| Borrow availability / utilization / cost-to-borrow / locates | ❌ | no vendor |
| Reg SHO threshold status | ❌ | not ingested (free; Stage 2) |
| Failures to deliver (FTD) | ❌ | SEC FTD files not ingested (free; candidate acquisition) |
| Options OI / volume / IV / Greeks / dealer gamma | ❌ | no options dataset (Cboe evaluation pending); opening/closing classification would require Open-Close product |
| Institutional ownership | ✅ delayed | 13F, 8 quarters, 45-day lag — **delayed quarterly disclosure, never live flow** |
| Insider ownership / transactions | ✅ US (PIT) | Form 4 via accepted_at; DSE insider-category disclosures |
| Recent dilution / ATM / converts / warrants / shelves | partial US | EDGAR filing events (S-1/S-3/424B/8-K forms) usable as **dilution-risk flags**, not parsed capital structures; DSE rights/RPO announcements |
| Lock-up expirations | ❌ | not modeled |
| Catalysts & filings | ✅ young | `research_catalyst_events` (DSE confirmed / US inferred), collection began Jul 2026 |
| Social attention | ✅ internal only | platform buzz — supporting context only, never positioning evidence |

Enforced language rules (encoded in code, not just prose): FINRA daily short volume ≠ short
interest; short volume cannot establish open short positions or days-to-cover; 13F is delayed
disclosure; options volume without opening/closing classification cannot prove new positioning;
social attention is context; missing borrow or options data produces an explicit
`data_blocked` family status, never a silent downgrade.

## C. Implementable squeeze families (current data)

| Family key | Market | Label shown to users | Grade |
|---|---|---|---|
| `compression_breakout` | US + DSE | "Compression breakout setup" | implement now (US survivorship caveat; DSE raw-close caveat) |
| `failed_breakdown_reversal` | US + DSE | "Failed-breakdown reversal" — **never** "confirmed short squeeze" | implement now |
| `supply_constrained_breakout` | DSE only | "Supply-constrained breakout" (verified free float + sponsor concentration exist) | implement now |

Elevated FINRA short-marked share (US) appears only as **supporting evidence text** on entries
of implementable families, worded exactly: "short-marked volume share elevated (X% 5-session,
volume-weighted) — this is not short interest and cannot establish positioning."

Since 2026-07-25 the implementable families also carry **real positioning evidence** when a
disseminated record exists: short interest as % of shares outstanding, days to cover, and the
change versus the prior settlement date, each stated with its basis and settlement date. Below
`SHORT_INTEREST_ELEVATED_PCT` the same line is filed as **counter-evidence** ("not elevated
positioning, so short-covering pressure is not a supported explanation"), and when no record
covers the session the entry says positioning is *unknown*, never low.

## D. Blocked squeeze families and missing data

| Family key | Blocked on | Expected value of unblocking |
|---|---|---|
| `us_short_squeeze` | **partially unblocked 2026-07-25.** Positioning has landed (short interest, days-to-cover, change vs prior settlement). Still missing: verified US free float, borrow/locate/cost-to-borrow, FTDs + Reg SHO | Registry status moved `blocked` → `diagnostic_only`, `implemented_strategy_key=None`. Two defects cap it below promotion: the ratio is of **shares outstanding** (no US free float), and positioning is fortnightly and up to ~2 weeks stale. **Short execution remains blocked** — identifying a squeeze setup and being able to borrow/locate/carry a short are different requirements |
| `us_gamma_squeeze` | option-chain history: OI, volume, expiry/strike, IV, delta/gamma; opening/closing classification for directional demand | Cboe products under evaluation (see `us-options-flow-research-2026-07.md`); any dealer-gamma sign must ship labeled as an assumption |
| `us_float_liquidity_squeeze` | verified US free float (insider/institutional lockups vs outstanding) | shares outstanding exists (PIT) but was **rejected as a float proxy** — treating outstanding as float systematically understates scarcity and would fabricate the family's core feature |
| crowded-institutional-unwind | positioning data at better than quarterly/45-day resolution | 13F depth (8 quarters) additionally too short |

These are registered in `bulls.analytics.strategy_readiness` and surfaced per market by the
squeeze monitor API with their missing-dataset lists. The API distinguishes two reasons so the
card never misstates why a family is absent: `data_blocked` (the core dataset does not exist)
versus `not_implemented` (the data landed but no evaluator has been built and, for the short
family, execution is still gated on borrow).

### Stage plan for the remaining short datasets

| Stage | Dataset | Cost | Unlocks |
|---|---|---|---|
| 1 ✅ done | FINRA consolidated short interest | free | positioning, days-to-cover, and the long books' crowded-short guard |
| 2 | SEC failures-to-deliver + Reg SHO threshold list | free | corroborating borrow-scarcity evidence |
| 3 | borrow availability, utilization, cost-to-borrow, locates (S3 / Ortex / S&P Global / IB) | paid | **the only stage that can unblock short execution** |

## E. Exact signal definitions (`squeeze-monitor-v3`)

All from completed EOD data; evaluated after each market's analytics refresh; deterministic;
thresholds are constants in `bulls.analytics.squeeze_monitor` restated in the API methodology.

Shared eligibility preconditions per ticker: analytics row fresh for the session; average
20-session traded value ≥ the market risk policy's `minimum_average_daily_value_mn`;
`sma_200` present with close above it (medium-term uptrend precondition for long-side setups).

**compression_breakout** (bars = last 120 completed sessions):
- *base*: `pct_from_52w_high ≥ -15` (within 15% of the 52-week high).
- *contraction*: ATR(14) now ≤ 0.8 × ATR(14) twenty sessions earlier, computed from the bar
  window (not the single stored value).
- *dry-up (supporting)*: `rel_volume_5d < 0.9`.
- *trigger price*: max high of the last 20 completed sessions (the base high).
- *states*: `watch` = base only; `forming` = base + contraction; `trigger_ready` = forming +
  last-5-session range ≤ 1.5 × ATR(14) + close within 3% below trigger; `confirmed` = a session
  within the last 3 closed above the trigger **and that same session traded ≥ 1.5× the base's
  average session volume** (v2: participation is measured on the breakout bar, not on whichever
  day the scan runs — see the reconciliation note below); `failed` = a previously
  archived `confirmed`/`trigger_ready` whose close falls below 0.97 × trigger;
  `exhausted` = close > 1.25 × sma_50, or 3-session gain > 20% with fading relative volume
  (< 1.0), or ≥ 2 of the last 3 sessions closing in the lower half of their range after a new
  20-session high (upper-wick persistence).
- *invalidation*: min low of the last 20 sessions (base low). *risk/share* = trigger −
  invalidation. *planning objective* = trigger + 2 × risk, labeled risk geometry.

**failed_breakdown_reversal**:
- *reference support*: min low of sessions −60…−11 (excludes the recent 10).
- *undercut*: any low in the last 7 sessions < 0.99 × support.
- *states*: `watch` = undercut occurred, price not yet back above support; `forming` = undercut
  occurred and latest close is back above support but below 1.02 × support; `confirmed` = latest
  close ≥ 1.02 × support with `relative_volume ≥ 1.2` (the reclaim, with participation);
  `failed` = latest close < the undercut low; `exhausted` as in compression. No `trigger_ready`
  (the setup is event-shaped, with no pre-breakout staging rung).
- The undercut window is `bars[-7:-1]`, excluding the current session, so the published
  invalidation cannot be set by the same bar that is being tested against it.
- The shared eligibility gate applies: this book only buys reclaims inside an intact
  medium-term uptrend, not every bounce in a downtrend.
- *invalidation* = undercut low; *trigger* = 1.02 × support.

**supply_constrained_breakout** (DSE only):
- preconditions + verified float: `free_float_cap_mn` present and `free_float_cap_mn /
  market_cap_mn ≤ 0.35` **or** `sponsor_pct ≥ 50`.
- compression states as above, plus *accumulation support*: `cmf_20 > 0` or `obv_slope > 0`
  (supporting evidence, not gating).
- float-turnover supporting metric: 20-session average traded value ÷ free-float value.
- Naming rule: this is a supply/demand condition; the words "short squeeze" never appear.

Counter-evidence (attached, never hidden): US — any S-1/S-3/424B* EDGAR filing by the issuer in
the last 90 days ⇒ "recent financing/dilution filing"; net insider open-market selling in the
last 30 days. DSE — negative `institute_delta`/`foreign_delta`; rights/RPO in recent
corporate-action disclosures. DSE-wide caveat: raw closes (no corporate-action adjustment) is
always listed under data quality.

State transitions are archived with a reason string; "why the classification changed" is the
diff between consecutive `squeeze_daily_states` rows.

### Reconciliation, 2026-07-26 (`squeeze-monitor-v2` → `v3`)

The `confirmed` branch previously ran before the near-52-week-high and ATR-contraction gates. That
made a high-volume 20-session high sufficient for confirmation even when no compression setup
existed. It also made the production monitor broader than the independently evaluated
`compression_breakout` hypothesis. Version 3 requires `near_high AND contraction AND breakout`
for confirmation. The DSE supply-constrained family inherits the same correction.

Reconstructed rows may be regenerated under v3 and remain explicitly marked `reconstructed`.
Forward rows retain the methodology that classified their session; they are not rewritten as if
v3 had existed earlier.

### Reconciliation, 2026-07-25 (`squeeze-monitor-v1` → `v2`)

An external review found the engine and this specification had diverged. Every divergence was
resolved in favour of whichever behaviour is defensible to a user, and the version was bumped
because these change which states the archive contains:

| Divergence | Resolution |
|---|---|
| Breakout confirmation joined "a close in the last 3 sessions cleared the base" to *today's* relative volume | Participation is now measured on the breakout session itself. The old form confirmed below-average-volume breakouts whenever an unrelated volume spike landed today, and printed a reason that was false about that breakout. |
| Failed-breakdown failed at `0.97 × support` while publishing `undercut_low` as its invalidation | Failure is judged on the published invalidation. A card must never show a level the engine does not enforce. |
| `undercut_low` included the current session, making the failure branch unreachable | Undercut window excludes the current session, mirroring the compression base. |
| Failed-breakdown skipped the shared eligibility gate | Gate applied. |
| Spec said the family has no `watch` state; the engine emitted one | Spec amended: `watch` is retained (undercut seen, not yet reclaimed, is genuinely informative); only `trigger_ready` is absent. |
| Archived rows read cap tier and capacity from the *current* analytics table | Both are snapshotted onto each row at scan time. Rows archived before the migration are null rather than backfilled, because they genuinely do not know their own session's classification. |
| "5-session" short-marked share actually covered a 9-calendar-day window | The measured session count is carried through and stated in the evidence line. |
| "Net insider selling" fired on any `S` transaction | 10b5-1 plan sales excluded; the line states it is not netted against purchases. |
| Card claimed a setup "maps to the registered us_breakout_v1 paper book" | Removed. No squeeze family feeds any book; the string implied an integration that does not exist. |

## F. Backtest methodology (specified; to run before any squeeze paper book)

Same institutional frame as `atlas-decision-archive-audit-2026-07-24.md` §H: point-in-time
universe, inactive/delisted inclusion (**blocked today for US — survivors-only store**),
next-session fills with measured half-spread + fee + ADV caps, split/distribution adjustments
(**blocked today for DSE**), dilution-event awareness, cap-tier and regime decomposition,
parameter ±25% sensitivity, walk-forward, untouched holdout, deflated-Sharpe correction,
capacity, MFE/MAE, failure rate, time-to-trigger and time-to-MFE distributions. Baselines the
complex model must beat at realistic and 30bps-stressed costs: market benchmark (SPY/DSEX),
cap-tier sleeve, random matched securities, simple momentum, simple high-relative-volume
breakout, equal-weight eligible universe. A squeeze model that cannot beat the simple
high-rel-volume breakout has no reason to exist.

## G. Backtest results

The module originally shipped without a backtest because the available store carried US
survivorship and DSE adjustment/depth defects. The independent 2026-07-25 diagnostics later
confirmed that restraint: US compression and failed-breakdown implementations were rejected;
DSE replay results were skewed and unstable.

The first registered broad `dse_compression_breakout_20d_v1` diagnostic failed. Its pre-correction
run produced 33 accepted entries and a measured-cost net return of -0.571%, versus +8.01% for
DSEX. That result remains in the audit trail but was superseded as the current diagnostic after
the 2026-07-26 archive rebuild removed standalone terminal episodes and reconstructed the latest
methodology causally across 260 sessions.

The post-rebuild run evaluated 186 first confirmations and accepted 77 entries. Over the same
493-session portfolio clock it returned +4.238% at an estimated 97.51 bps one-way measured cost,
versus +8.01% for DSEX: -3.772 percentage points of excess return, 0.449 Sharpe and 5.422% maximum
drawdown. Train/validation/test absolute returns were -3.420% / +5.187% / +2.607%, which is
unstable rather than uniformly positive. A hypothetical feasible 50 bps one-way run returned
+9.592%, but the measured-cost result is authoritative. Stress scenarios below DSE's mandatory
40 bps fee floor are impossible and are now omitted instead of being published under false
10/30 bps labels. The forward book remains paused.

`dse_selective_compression_v1` is a separate preregistered candidate, not a relabeling of the broad
book. It caps the portfolio at three names, suppresses maintenance trades inside a 20% target band,
and ranks causal first confirmations using DSEX-relative strength, breakout volume, base-volume
contraction, CMF, OBV flow, close location, extension, liquidity and market regime. Before even a
diagnostic forward book may start, the fixed rule must have at least 12 qualified entries and 10
executed entries; positive measured-cost full, validation and untouched-test excess returns;
positive return at 30 bps one-way cost; <=8% drawdown; >=0.80 deflated-Sharpe confidence; and beat
both the five-session-delay and liquidity-only three-slot nulls at realistic and stressed costs.
Failing any check records `not_admitted` and creates no book.

The first production v1 diagnostic on 2026-07-26 returned `not_admitted`. Across 260 reconstructed
sessions it evaluated 186 first confirmations but qualified zero. The first-failure attribution was
90 stop distances above 10%, 42 below the BDT 5M liquidity floor, 24 without the required base
contraction, 14 below DSEX relative strength, and 16 across volume/CMF/stop-width gates. This is a
useful falsification of the frozen conjunction, not evidence that thresholds should be loosened
until a backtest turns green. No selective shadow book exists. A v2, if investigated, must choose
changes using training-only feature availability, register a new trial, and leave validation and
test outcomes untouched until the specification is frozen.

Every daily state continues to be archived point-in-time. No profitability claim is permitted
until next-observable execution, costs, benchmark, capacity and portfolio constraints pass the
mandate's forward gates.

Forward rows are immutable. Re-running a completed session cannot relabel evidence after observing
the outcome; a live scan may only replace a reconstructed placeholder for the same session. A
methodology revision begins on the next unobserved session, while archived rows retain the version
that classified them.

A replay replacement is atomic and window-complete: it removes prior reconstructed rows in the
requested session window and writes the new methodology in one transaction. This prevents stale
rows that no longer meet the revised rules from surviving beside the corrected archive.

## H. Agent and typed-contract design

Deterministic evaluator: `bulls.analytics.squeeze_monitor` — pure functions, no I/O:
`SqueezeInputs` → `SqueezeAssessment` (family, state, prices, evidence lists, missing-evidence,
reason). LLMs are not involved anywhere in this module; explanation strings are assembled from
measured values. Contracts (Pydantic): `SqueezeAssessment` (analytics),
`SqueezeDailyState` ORM row (core), `SqueezeMonitorOut / SqueezeFamilyOut / SqueezeEntryOut`
(API). The scan task is the only writer; the API is read-only; the UI renders the contract
verbatim. Per-ticker output includes: market, ticker, company, cap tier, family, state, first
discovered date + price, first confirmation, next observable session open, gross follow-through
from that observable reference, as-of date, setup price, trigger price/condition, invalidation,
risk per share, planning objective (risk geometry, never a target), expected holding window, data
quality notes, liquidity capacity (2% ADV participation), supporting evidence, counter-evidence,
catalyst proximity, dilution flags, missing evidence, explanation, and methodology version.

The next-observable return is a diagnostic path measurement, not a simulated fill or portfolio
P&L. It excludes fees, slippage, capacity, cash, concurrency and risk constraints.

## I. Paper-trading integration

The squeeze list never auto-creates a target. It remains broad research inventory even when a row
is `confirmed`; most rows should be rejected by a selective strategy. The failed broad v1 book is
paused. The selective v1 candidate can create a diagnostic forward book only after the historical
admission gate in §G passes. New immutable `squeeze-monitor-v3` confirmation transitions on or
after registration are then ranked under the frozen rule, with execution no earlier than the
following session open. Research discovery, quality qualification, target formation and completed
paper fill remain separate states in the decision archive.

### Setup chart (`SqueezeChart`, added 2026-07-24)

A squeeze setup is a technical thesis, so the detail pane renders the evidence rather than only
asserting it: daily candlesticks, EMA 20/50, anchored VWAP, a volume histogram, the trigger and
invalidation levels, state-transition markers, and an OHLC + ATR-change readout. Overlays are
computed server-side in `bulls.analytics.chart_overlays` so the chart and the evaluator cannot
drift apart. Rules that must survive future edits:

- **Never label the purple overlay plain "VWAP".** It is an *anchored* VWAP built from daily
  typical price x volume, anchored at first discovery. A true VWAP is intraday and session-based;
  Atlas has effectively no intraday history (§B). The UI and the API `overlay_basis` both say so.
- **Only operational levels are drawn** — trigger (where the setup activates) and invalidation
  (where it dies). The 2R planning objective is deliberately *not* a chart line: it is derived
  arithmetic already reported in the metrics, a line reads as a price forecast, and it commonly
  falls outside the autoscaled range so the line would be invisible as often as not.
- Overlays return `None` before their lookback exists rather than seeding a value, so no average
  is drawn over history that did not exist.
- The window ends at the archived session, so selecting a past date can never reveal later price
  action, and the DSE raw-close caveat is restated in `price_basis`.
- Only genuine state *transitions* become markers; repeating an unchanged state every session
  would bury the progression.
- **Discovery is per-episode, and a ticker can be discovered many times.** An episode ends at a
  terminal state (`failed`/`exhausted`/gone); a fresh formation afterward is a *new* discovery
  with a new `first_discovered_on`, not a continuation of the old one. `resolve_episode`
  (`bulls.analytics.squeeze_monitor`, unit-tested) is the single rule the scan uses, so the
  buggy carry-forward that kept a stale discovery date across a fail→reform is gone. The chart
  labels every visible episode with compact markers (`D1` discovery, `T1` trigger-ready, `C1`
  confirmed, `F1` failed, `X1` exhausted) while muting prior episodes. It keeps the current
  episode's dotted discovery price line and states "Nth discovery … at {price}" above the chart.
  `prior_discovery_dates` surfaces how many earlier setups this ticker/family had. Prior episodes
  remain separate archived rows, reachable by the archive-date selector.

## J. Atlas UI specification

"Squeeze monitor" panel (investment command page): market-appropriate family tabs (blocked
families rendered as explicit data-blocked cards with their missing datasets, not hidden);
state filter; capitalization filter; archive date selector over `squeeze_daily_states` dates;
default "New today" view containing first discoveries and first confirmations on the selected
date; explicit "Confirmed means rule completed, not high probability" and "No order is created"
execution boundary; days since discovery; return / MFE / MAE since discovery (bar-derived, basis
labeled); numbered multi-episode setup→trigger progression (state history);
trigger/invalidation/planning levels
(2R labeled "not a forecast"); supporting and counter-evidence; dilution warnings; data-quality
notes; paper-book status (registered DSE forward diagnostic or no book). Wording rules from §C/§D are part of
the spec: "Potential short squeeze" only ever with authoritative short-position evidence (i.e.,
never, until `us_short_squeeze` unblocks); "too extended" surfaces as the `exhausted` state.

## K. Code and tests completed

| Component | File | Verification |
|---|---|---|
| Deterministic evaluator | `packages/analytics/src/bulls/analytics/squeeze_monitor.py` | `packages/analytics/tests/test_squeeze_monitor.py` — 11 tests incl. a guard that no family ever emits "short squeeze", exhaustion detection, and the exact FINRA disclaimer wording |
| Archive table | `packages/core/src/bulls/core/models/squeeze.py` + migration `c4e6a8b0d2f4` | PK `(market, code, family, as_of_date)`; closed sessions never rewritten |
| Scan task (only writer) | `services/ingestion/src/ingestion/squeeze_scan.py` | DSE cron 13:22 UTC (`worker.py`, after `refresh_analytics`); US inside `run_us_eod_chain` after `compute_all`, wrapped so a failure logs and the EOD chain continues |
| API read model | `services/api/src/api/institutional_research/squeeze.py` + `GET /institutional-research/squeeze-monitor` | `services/api/tests/test_squeeze_monitor_api.py` — blocked-family contract + language rules |
| Readiness registry | `strategy_readiness.py` (+5 squeeze entries) | `test_strategy_readiness.py` invariants |
| UI | `apps/research/src/features/investment-command/SqueezeMonitorPanel.tsx` | Verified in preview both tenants: DSE renders 3 available families and the string "short squeeze" appears nowhere on the page; US renders the blocked short-squeeze card with its 3 missing datasets and zero entries |
| DSE broad diagnostic | `packages/analytics/src/bulls/analytics/dse_compression_breakout.py` + `services/api/src/api/institutional_research/dse_squeeze_backtests.py` | Failed historical result retained; broad forward book paused |
| DSE selective candidate | `packages/analytics/src/bulls/analytics/dse_selective_compression.py` | Causal quality features; three-position ranking; 20% rebalance band; chronological validation/test; cost, drawdown, deflated-Sharpe and two-null admission gate |

Two engine defects were found by the tests during implementation and fixed: the base high/low
must exclude the most recent 3 sessions (otherwise a breakout raises its own trigger and can
never confirm), and breakdown failure must key off the support level rather than the wick low.

## L. Remaining risks

1. Setup-quality claims are unvalidated until §F backtests run on repaired data — the UI says
   "diagnostic taxonomy" and shows no performance promises.
2. US universe survivorship means archived US setups over-represent survivors until delisted
   histories land.
3. DSE raw closes can flip states across bonus/rights ex-dates (listed in every DSE entry's
   data-quality notes; fixed by the DSE adjustment backfill, P1 of the main report).
4. Threshold constants are v1 priors, not fitted values; any change is a new methodology
   version and restarts the affected family's forward archive interpretation.
5. FTD + bi-monthly short interest are cheap partial unblocks for `us_short_squeeze`; without
   borrow-cost data the family still cannot claim confirmed squeeze mechanics.

## M. Deployment checklist — folded into the main report's §M (same release).
