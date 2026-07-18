# Atlas investment authority and release boundary

Status: accepted architecture decision

Recorded: 18 July 2026

This decision defines which system is allowed to become the investment authority, what the
existing Hedge application means, and how the July 2026 institutional foundations are released.
It does not authorize broker connectivity, real capital, or external performance claims.

## Decision

Atlas is the canonical future investment operating system.

Hedge is a frozen legacy paper experiment. Its historical publications, orders, fills and
performance must be preserved as evidence, but Hedge is not an alternative source of portfolio
truth and its track record must not be merged into an Atlas strategy. A Hedge idea can enter Atlas
only as a newly registered hypothesis with a new immutable specification, point-in-time test and
Atlas shadow book.

Atlas remains paper-only. Deterministic strategy, portfolio, accounting and risk code is
authoritative. An AI model may investigate evidence, propose a registered hypothesis and explain a
decision, but it may not invent a fill, mutate cash, size a position, override a constraint or send
an order to a broker.

The current delivery scope is DSE only. US experiments and implementation artifacts are parked and
remain market-isolated until the DSE foundation is complete. Reusing this engine for another market
later means reusing contracts, not data, calendars, parameters, evidence or portfolio state.

## Source-of-truth matrix

| Domain | Authoritative source | Projection or consumer | Explicit non-authority |
|---|---|---|---|
| Security identity and eligibility | Effective-dated security master and market-scoped universe records | Research queue and strategy universe adapters | A current ticker list reconstructed backward |
| Daily market history | Point-in-time daily bars plus market calendar and corporate-action policy | Backtests, dossiers and EOD shadow reconciliation | Portal cards or cached chart payloads |
| DSE intraday research | Immutable delayed quote observations; sampled 15-minute projections are derived | Intraday readiness and future hypothesis tests | The latest quote table, synthetic historical bars or exchange-native OHLC claims |
| Company evidence | Immutable source snapshots and claim/source-span lineage | Dossiers, autonomous research and thesis memory | LLM prose without a cited evidence pack |
| Strategy definition | Registered immutable trial specification and methodology version | Backtest and shadow engine | A prompt, owner preference or undocumented parameter search |
| Investment mandate | Versioned mandate pinned to a trial and shadow book | Portfolio and risk engine | A later mandate silently applied to old results |
| DSE fund research target | Deterministic sleeve budgets plus shared cash, name, sector and gross constraints | Diagnostic target and intervention report | An order, fill, paper book, capital allocation or promotion decision |
| Cash, positions, fees and settlement | Ordered append-only accounting events, replayed before a snapshot is accepted | Shadow snapshots, NAV and attribution | A snapshot-derived decision narrative |
| Signal-to-outcome narrative | Snapshot-linked decision audit events | Investment Command and audit review | The accounting ledger or proof that an event existed before the snapshot |
| Promotion decision | Versioned promotion policy and immutable historical/forward evidence | Strategy Lab eligibility report | Automatic capital allocation |
| Real execution | None exists | None | Any Atlas or Hedge paper fill |

## Production and working-tree boundary

The production facts checked on 18 July 2026 form the pre-change methodology boundary:

| Capability | Production boundary | Working-tree target |
|---|---|---|
| Atlas database revision | `c8f2d5a7e9b1` | Intraday release first, accounting/settlement release second |
| DSE daily history | Existing server history remains in place | Reuse it; no full redownload is required |
| DSE listing history | Current universe only; no historical observation rows | Start validated effective-dated observations forward; never synthesize prior membership |
| DSE intraday history | Latest delayed quote snapshot only; no retained history | Begin immutable collection after the intraday release |
| Atlas paper books | No DSE Atlas shadow portfolio was present in the production tenant on 18 July 2026 | Do not fabricate or backfill one; a future book requires a passed immutable admission report and a declared inception date |
| Hedge | Separate legacy paper experiment | Freeze new strategy development; preserve read-only history |
| Decision events | Snapshot-derived audit projection begins at reconciliation | Keep the projection labelled honestly; add an independent accounting ledger |

Performance and methodology before and after either release must be reported separately. The
intraday collector cannot backfill history that was never retained. The accounting release cannot
retroactively claim event-first lineage for snapshots created before its deployment.

## Global experiment register

The portfolio is intentionally small. States are global governance states, not marketing labels.

| Experiment | Owner system | State | Admission decision |
|---|---|---|---|
| `dse_reversal_v1` | Atlas | registered diagnostic; inactive | Preserve its specification and rejected January 2025–present proxy. Do not create or backfill a book on the current evidence. |
| `us_breakout_v1` | Atlas | active diagnostic | Continue unchanged and collect forward evidence. |
| `us_leader_capture_v1` | Atlas | candidate diagnostic | Daily trend plus point-in-time reported acceleration. Automation remains blocked; complete unbiased historical validation before promotion. |
| `quality_reversal_eod` | Hedge | frozen legacy | Preserve history; no new Hedge variants or Atlas track-record merge. |
| `dse_trend_pullback_intraday_v1` | Atlas | data blocked | Collect honest intraday history, preregister, then test. No daily proxy. |
| `dse_quality_value_v1` | Atlas | candidate | Requires point-in-time publication knowledge and costed diagnostics. |
| `dse_pead_v1` | Atlas | data blocked | Requires deep timestamped earnings and surprise history. |
| Generic DSE momentum/breakout variants | None | rejected diagnostic | Preserve failed research; do not reactivate by renaming parameters. |

The initial maximum remains three concurrent Atlas shadow books per market workspace. A frozen
Hedge experiment does not consume an Atlas runtime slot, but it does count in research-governance
reporting so the owner sees every live or legacy experiment in one inventory.

The strategy registry owns five independent contracts: market, scorer, holding/selection policy,
sizing policy, and required evidence. An unknown strategy or policy fails closed. A new key cannot
fall through to another strategy's scorer. `us_leader_capture_v1` is the first strategy using the
expanded contract: monthly buffered holdings, mandate-level equal sizing, and SEC facts replayed
only after their recorded knowledge time. Its DSE analogue is not executable because comparable
timestamped quarterly acceleration evidence is not yet complete.

## Independent release sequence

### Release A: DSE intraday observation foundation

This release may deploy without the accounting change. It creates immutable delayed quote
observations, sampled 15-minute projections and session-quality audits. Capture runs beside the
existing quote update. A failure in intraday storage must roll back only the intraday savepoint;
the portal quote and daily ingestion paths continue and the failure is reported.

Acceptance gates:

- migration rehearses successfully on a production-shaped snapshot;
- duplicate capture is idempotent and cannot double-count volume or turnover;
- provider counter regression is retained and labelled, not converted into negative flow;
- missing intraday tables or a write error does not stop the existing quote update;
- bars are labelled sampled delayed observations, never exchange-native OHLC;
- no strategy signal, target, order, fill or shadow book is created from the new data;
- readiness remains blocked until the preregistered strategy's coverage policy passes.

### Release B: Atlas accounting and settlement authority

This release follows Release A and may be rolled back independently. It adds settlement-aware
state and an ordered append-only accounting ledger. Accounting events are constructed and replayed
before a new shadow snapshot is accepted. Snapshot-linked decision events remain a useful audit
projection but are not relabelled as the cash or position authority.

Acceptance gates:

- DSE T+2 and US T+1 receivables release on the correct completed session;
- unsettled sale proceeds cannot fund a same-session buy;
- a balanced buy basket is independent of symbol iteration order;
- fees, turnover, positions, settled cash and receivables replay exactly from accounting events;
- retrying one session produces the same event keys and no duplicate economic event;
- a missing held-security bar pauses the book rather than fabricating a mark or fill;
- historical snapshots stay unchanged and receive no invented event-first history;
- promotion remains an eligibility report with `capital_action = none`.

## Five-session reconciliation after each release

For five consecutive completed market sessions, the operator records:

1. expected and observed collector/reconciliation run identifiers;
2. latest daily and intraday knowledge cutoffs by market;
3. intraday slots, symbols, freshness, VWAP coverage, regressions and isolated failures;
4. every signal, target change, rejection, fill, settlement release and ending position;
5. prior cash plus releases minus buys and fees versus ending settled cash;
6. prior positions plus fills versus ending positions;
7. receivables created, released and remaining by release session;
8. NAV, benchmark, exposure and drawdown versus the accepted snapshot;
9. retry result and duplicate-event count;
10. any difference, its owner and whether the book was paused.

Any unexplained accounting difference, cross-tenant reference, missing held-security mark, or
silent collector failure fails the release. A strategy losing money does not by itself fail an
operational release; hiding or mis-accounting for the loss does.

## Explicitly deferred

- broker connectivity or real capital;
- new strategy variants created to improve the appearance of results;
- merger of Atlas and Hedge performance;
- synthetic intraday history;
- executable fund-level capital allocation, financing or portfolio-of-portfolios performance claims;
- LLM authority over calculations, targets, risk or execution;
- promotion based only on the early 60-session/10-execution review floor.

The 60-session/10-execution thresholds are an early evidence review floor, not a sufficient
investment-committee standard. Capital consideration requires deeper regime coverage, stronger
statistical evidence, capacity and cost stress, operational reconciliation and a separately
authorized investment decision.

The local DSE sleeve aggregator is narrower than the deferred capability: it produces one
deterministic, non-executing research target with `capital_action = none`, while recording which
sleeve requests were reduced by shared limits. It creates no order, fill, shadow book or performance
series and therefore does not establish a fund track record.
