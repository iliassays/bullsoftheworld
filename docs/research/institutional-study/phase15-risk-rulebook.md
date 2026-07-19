# Phase 15 — Risk Rulebook

**Date:** 2026-07-19. Every number below is a **hypothesis with a conservative/moderate/
aggressive range**, never an institutional fact — the study's single most repeated finding is
that real institutional limits are proprietary (U) and the circulating numbers are folklore
(Phase 9's empty pod-rule hunt). What *is* evidence-backed is the **structure**: which rules
exist, what they respond to, and that they execute without appeal. Numbers get fixed per-system
at preregistration (Phase 13) and revised only through the versioned-spec process.

Design principles (each cites its evidence):
- Rules respond to **observables that need no forecast** — P&L, spread, ADV, position weight
  (the platform grammar's transplantable property — Phase 5 finding 4).
- Breach ⇒ action executes by default; **overriding the action needs a written case** — the
  inverted veto from Sequoia's post-mortem reform (Phase 7 finding 4).
- The rulebook is a **conjunction-breaker** (Phase 11.A.6): at all times at least leverage and
  shorting are hard-capped at zero, so no failure-signature conjunction can complete.

## L1 — Position rules

| Rule | Conservative | Moderate | Aggressive | Evidence anchor |
|---|---|---|---|---|
| Max position at cost (event books) | 3% | 5% | 8% | Phase 5 §5.4 (5–10% concentrated hypothesis range); Sequoia 32% as the disaster print |
| Max position at cost (factor sleeve) | 1.5% | 3% | 4% | Phase 5 (1–3% diversified) |
| Liquidity: max position vs ADV | exit in 1 day at ≤10% ADV | 1 day at ≤20% | 2 days at ≤25% | Phase 6 days-to-exit grammar; Archegos negative print |
| Tradeable gate | spread ≤50bps & price floor | ≤100bps | ≤150bps | Phase 7 §7.5 (spread is retail's real cost); portfolio's own is_tradeable finding |
| Earnings/binary events | no entry within 5 sessions pre-event; size unchanged if held | same, size-aware | hold through with thesis note | Phase 6 L1 (event as sizing input) |
| Shorting | **0 (hard, all tiers)** | 0 | 0 | Phase 10 VW/GME; Phase 11.B preconditions absent |
| Leverage | **0 (hard, all tiers)** | 0 | 0 | Failure signature (Phase 11.A.6); LTCM/Archegos |

## L2 — Book rules (per system book)

| Rule | Conservative | Moderate | Aggressive | Anchor |
|---|---|---|---|---|
| Drawdown ladder: halve gross at | -6% from book HWM | -8% | -12% | Platform grammar (SI/WI — folklore-labeled); AQR/Tiger contrast (Phase 6 L2) |
| Flatten & freeze at | -10% | -12% | -18% | same; freeze ⇒ written review before any re-entry |
| Concurrent positions cap | A:12 / B:8 / C:30 | 20/15/50 | 25/15/60 | Phase 5 archetypes; 1/N evidence |
| Factor-lens review | monthly | monthly | quarterly | Tiger 2022 thematic-correlation failure (Phase 6) |
| Crowding screen at entry | SI>15% of float excluded | >20% | >25% | Melvin; VW; public-data-was-available finding |
| Cash is a valid state | unlimited idle time | same | same | Mandate anti-entertainment rule; System B episodicity |

## L3 — Process rules (no ranges — these are structural, evidence says binary)

1. **Pre-registered invalidation per position** before entry (Phase 4 step 9/24; Greenlight MS);
   trigger *type* determines exit speed (thesis-break = immediate & full; valuation = staged —
   Phase 7 finding 3). Never execute a thesis-break exit on a valuation timetable.
2. **Independent-of-author check:** every entry above minimum size gets its downside case
   reviewed against the written spec by the *system* (automated checks are the independent
   reviewer at our scale) — the Phase 11.A.1 invariant implemented honestly for a solo operator:
   the rules are the second pair of eyes, which is exactly why they must be written first.
3. **Re-underwriting before any add to a loser,** in writing, passing all seven conditions of
   the Phase 6 test — else the add is refused by default.
4. **Override log:** any manual deviation is an event with a written reason, reviewed quarterly
   (Phase 13.4). Repeated same-reason overrides ⇒ the rule gets formally revised or the operator
   stops — silent erosion is the documented death (Amaranth's overridden risk function).
5. **Post-mortem file per killed system and per >5% single-position loss** (PSH/Bridgewater/
   Greenlight documented practice — Phase 4 step 25).

## L4 — Operational rules

1. **Change control + kill switch:** no strategy-code change reaches the live loop without a
   versioned spec bump; a one-command flatten-all exists and is tested quarterly (Knight
   Capital, Two Sigma — V, Phase 6 L4).
2. **Broker/venue redundancy** appropriate to scale; credentials and data feeds documented so
   the system survives its operator's laptop (the retail version of counterparty diversification).
3. **The behavior-gap countermeasure:** entries and exits execute from the system, not from a
   phone at 2am. Manual market orders in system names are overrides by definition (L3.4).
   Anchor: the largest documented return leak in the study is operator timing (Phase 9/11).

## Review clause

This rulebook is versioned with the specs it governs. Ranges harden into numbers at each
system's preregistration; the numbers may move only via the written revision process, and every
revision cites either new primary evidence or the override log. The rulebook's own success
metric is negative: **the interesting result is every catastrophe that doesn't happen** — which
is why the override log and breach log, not returns, are its KPIs.
