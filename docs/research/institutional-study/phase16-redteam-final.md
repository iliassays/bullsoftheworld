# Phase 16 — Red-Team Pass + Final Ranked Recommendations

**Date:** 2026-07-19. This closes the study: (1) resolution of the standing verification IOUs,
(2) adversarial review of the study's own weakest structures, (3) final recommendations ranked
by evidence strength, (4) the standing-uncertainty register that survives the study.

## 16.1 Verification IOUs — resolved this pass (primary PDFs fetched)

1. **FIM per-trade costs (Phase 7 IOU) — RESOLVED, with a version trap worth recording.** The
   circulating "median 6.24 bps NYSE / 6.16 bps Nasdaq" IS in the paper — but only the
   **Oct 2015 draft** (Table II, Aug 1998–Sep 2013 sample), not the 2012 draft and not the 2018
   "Trading Costs" paper (whose medians are **5.06/5.03, overall median 6.18, mean ~10**).
   Break-even capacities also drift across drafts (2015: SMB $275B/HML $214B/UMD $56B; 2012:
   $103B/$83B/$52B). **Lesson institutionalized:** working papers are moving targets — cite
   version + table or don't cite. Ledger updated with the per-version figures. The Phase 13
   Patton–Weller-pessimistic cost rule is *unchanged* — verified AQR medians of ~5–7 bps are an
   elite implementer's costs, not ours.
2. **Citation spot-checks (Phase 2/3/5 load-bearers) — all three VERIFIED:** Khandani–Lo is JFM
   14(1) 2011 and says what we claimed (simultaneous factor-crowded unwind); DeMiguel–Garlappi–
   Uppal RFS 2009 confirmed (none of 14 optimizers consistently beats 1/N OOS; ~3,000–6,000
   months of data needed for MV to win); Cusatis–Miles–Woolridge JFE 1993 confirmed — spun-off
   entities +33.6% matched-firm-adjusted at 36 months (t=2.31). **Material nuance recovered:
   the 6- and 12-month excess returns are INSIGNIFICANT (-1.0%/+4.5%); the drift concentrates in
   year 2.** System B's entry window is therefore not "at spin" but into the post-spin
   forced-selling trough — this changes the preregistered spec and is exactly why the red-team
   pass exists.
3. **13F-cloning recency (Phase 8 IOU) — resolved as follows:** the claimed "2021 JFE version"
   of Best Ideas is **REFUTED** — it remains HBS WP 21-004 (sample extended to Dec 2018; effect
   held at ~2.8–4.5%/yr; never a JFE publication). Post-2015 evidence overall: working-paper
   grade and mildly positive (Jivraj et al. to 2019; Schroeder–Posch 2013–23 — treat their
   headline number skeptically), with a **peer-reviewed counterweight**: 13F-visible crowding
   predicts weaker subsequent anomaly returns (J. Banking & Finance 2025). System A's kill
   criteria already assumed this uncertainty; now it's documented rather than assumed.
4. **Regulatory currency — both confirmed for mid-2026:** 13F threshold still $100M (the 2020
   $3.5bn proposal was never adopted); the 2023 13D/G deadline amendments are in effect and
   **unchallenged** (no suit found; SEC staff conformed 18 C&DIs to them July 2025) — phrase as
   "in effect, unchallenged," not "survived challenge."

## 16.2 Red-team: the study's own weakest structures

1. **The silent middle is missing.** We studied famous survivors and famous failures; the
   thousands of unremarkable funds that quietly returned nothing and closed are in neither
   column. Every "invariant" is therefore conditioned on *documented* institutions — the
   inference "do X and survive" is weaker than it reads. Mitigation: the invariants we kept are
   mechanistic (caps, pre-commitment, downside-first), not performance claims.
2. **Attribution inflation pervades the activism record** (flagged in Phase 9, repeated here):
   outcomes labeled V are events; causal credit is contested in every campaign. System A's
   thesis deliberately relies on the *event-study return*, not on activists being right.
3. **The self-reported tier is load-bearing in places.** Elliott's loss years, TCI's -43%,
   platform internals — MS/SI at best. The study's defense is the labeling itself; the residual
   risk is that labeled folklore still anchors thinking. The pod-ladder *numbers* in Phase 15
   are the clearest case: they inherit folklore ranges, and we said so, but a future reader may
   forget.
4. **Single-sprint research risk.** Phases 7–16 were researched in one day by web agents.
   Primary anchors were fetched for the most load-bearing claims (SEC FAQ, adopting releases,
   PSH letters/ARs, Third Point's sheet, Senate PSI, FIM PDFs, Treasury CAP paper), and three
   fabrication-shaped errors were caught in-flight (the $2.6bn GGP contamination, the fake
   "+45% Third Point 2008," the "$4.70 GME exit"). But secondary-sourced numbers remain
   throughout. **Standing rule inherited by all future work: no ledger row graduates from SI to
   V without a fetched primary, and any row that feeds a capital decision gets re-verified at
   decision time.**
5. **The three systems are untested hypotheses and the study must not be quoted as if they
   work.** The deliverable is the ledger, the invariants, and the process — not a prediction.
   Per Phase 12's own expectation: if all three pass their forward tests, audit the harness
   before celebrating.

## 16.3 Final recommendations, ranked by evidence strength

**Tier 1 — adopt unconditionally (invariant-grade evidence, costless):**
1. **The conjunction-breaker rulebook** (Phase 15): leverage 0, shorting 0, written caps,
   drawdown ladder, override log. Anchored by the failure record — the strongest evidence class
   in the study (V, autopsies).
2. **Pre-commitment as infrastructure:** preregistration-by-commit, invalidation written before
   entry, trigger-type-sets-exit-speed. Anchored by Phase 11.A.5 and the Druckenmiller-2000
   counterfactual.
3. **Execution hygiene** (Phase 7): limit orders, never the open, prefer the close, spread-gated
   universe, size to 1-day exit. Retail's one structural advantage, free to keep.
4. **Null-first benchmarking:** the index floor (NBIM's proof) and 1/N (DeMiguel, verified).
   Anything that can't beat both after stressed costs parks — abstention is a result.

**Tier 2 — paper-test as designed (conditional evidence, real open questions):**
5. **System A (13D event stream)** — the best free signal found (peer-reviewed, non-reversing,
   regulation-improved), with the follower-capturable share as the honest open question.
6. **System B (spin-off/forced-seller)** — spec amended this phase: entry targets the post-spin
   trough, drift expectation concentrated in year 2 (Cusatis, verified).
7. **Form 4 opportunistic-cluster filter** — every refinement computable free; modern-era decay
   disputed; cheap to test, cheap to kill.
8. **System C (factor sleeve)** — honestly beta-plus; primarily the vehicle for the risk grammar
   and the null-measurement discipline.

**Tier 3 — documented don'ts (rejection is the recommendation):** shorting in any form, leverage
in any form, alt-data speed races, large-cap PEAD, whole-portfolio 13F cloning, index-inclusion
trading, discretionary macro. Each rejection carries its evidence in Phase 12 §12.4.

## 16.4 Standing uncertainties that survive the study (inherit and maintain)

- Platform internals (pod numbers folklore; documented absence of primary).
- Famous-trade P&L opacity (Phase 10 §10.4 list).
- Medallion post-2024 (U).
- 13F-cloning modern efficacy (working-paper positive, peer-reviewed crowding negative —
  System A/its kill criteria are the live experiment).
- Insider-alpha modern decay (disputed — Form 4 sleeve is the live experiment).
- N-PORT disclosure cadence (in regulatory flux — re-check before any dependence).
- Everything in this study dated 2026-07-19 decays: regulatory rows re-verified annually,
  return rows at citation time (Phase 14 Stage 4 loop).

---

**Study complete: 16/16 phases.** The ledger (95+ rows), the six invariants, the conditionals
table, three preregistration-ready system specs, a versioned risk rulebook, and a staged
roadmap — every claim labeled, every disagreement preserved, every number that couldn't be
verified marked U instead of guessed. Per the assignment's evidence rules: nothing was fabricated,
and "not publicly available" appears wherever it is the truth.
