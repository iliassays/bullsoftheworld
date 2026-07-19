# Phase 5 — Portfolio Construction

**Date:** 2026-07-19. Labels V/MS/SI/WI/U per Phase 1. Central finding stated up front: **across
every documented case, construction and sizing — not stock selection — determined survival.**
Valeant was a bad pick for many funds; it was *fatal* only where sizing let it be (Sequoia >30%,
PSH ~20%+). GME shorts hurt many funds; they *killed* the one sized without squeeze limits.

## 5.1 Sizing methods — who documentably uses what

| Method | Documented user (evidence) | Notes |
|---|---|---|
| Equal weighting | Academic benchmark (V: DeMiguel et al. 2009 — 1/N beats most optimizers OOS) | Institutions rarely admit to it; the evidence for it is embarrassingly strong at small N |
| Conviction weighting | PSH: 8–12 core positions (V, annual reports); TCI: top-10 ≈ whole book (V, 13F) | The math is informal; the discipline is the max-position cap |
| Volatility-based sizing | Platforms, AQR, CTAs (V methodologically in AQR research; SI for internal practice) | Position ∝ 1/vol; the workhorse of systematic sizing |
| Risk-contribution / risk parity | Bridgewater All Weather (MS/V-method, published papers) | Asset-allocation layer, not stock selection |
| Mean-variance optimization | Almost nobody in raw form (SI) — estimation error dominates (V academic: Michaud 1989 "error maximization") | Used with heavy constraints/shrinkage if at all |
| Kelly / fractional Kelly | Thorp's Princeton Newport (V, his own accounts + record); Buffett/Munger implicit endorsement (MS, quotes) | Full Kelly assumes known edge; institutions that survived used ≤ half-Kelly-equivalent sizing (SI) |
| Factor/beta/dollar/sector neutrality | EMN and platform pods (V methodologically; SI internally) | Construction as constraint-satisfaction |
| Liquidity-adjusted sizing | NBIM (V, published frameworks); platforms (SI): size ≤ x days of ADV | The Archegos negative: >10% of float via swaps (V, court records) |
| Drawdown-adjusted (de-risking schedule) | Millennium-style: -5% halves capital, -7.5% terminates pod (SI — consistent across many secondary sources, **no primary doc**) | The platform's core invention: sizing is a *function of recent P&L* |
| Scenario-loss sizing | Amaranth had it and overrode it (V, Senate PSI) | The tool existing is not the tool governing |

## 5.2 Verified construction parameters by institution

| Institution | Positions | Max single position (documented) | Exposure/leverage | Source quality |
|---|---|---|---|---|
| Berkshire | ~40 public equities + subsidiaries | **Apple ≈ 50% of public-equity book at 2023 peak; ~40% of firm value** (V, 13F + [CNBC](https://www.cnbc.com/2024/05/04/warren-buffetts-berkshire-hathaway-cut-apple-investment-by-about-13percent-in-the-first-quarter.html)); trimmed ~2/3 during 2024, stated partly tax-motivated (MS) | No portfolio leverage; float as structural funding (V) | 5 |
| Pershing Square (PSH) | 8–12 | ~20%+ at cost historically (Valeant era); post-Valeant caps stated in ARs (V) | Modest; index put/CDS overlays episodically (V, ARs) | 5 |
| NBIM | ~8,000–9,000 equities | **≤10% of any company (hard rule)**; expected relative volatility ≤ **1.25pp** vs benchmark (V, [mandate/NBIM](https://www.nbim.no/en/investments/risk-management/)) | Unlevered | 5 |
| Yale | Policy-portfolio weights across asset classes; manager-level delegation (V, reports) | Asset-class bands, disciplined rebalancing to policy (V/MS, Swensen's book) | Illiquids ~50%+ (V, reports) | 5 |
| TCI | ~10–15 | Top positions >15% each visible in 13F (V, position side only) | Modest net-long | 4 (13F shows longs only) |
| Greenlight | ~30–40 longs, similar shorts (MS, letters) | "Significant" concentration top-5 longs (MS); numeric cap U | Gross ~150%, net ~70–100% typical (MS-era letters, varies) | 3 |
| Millennium/Citadel | 1000s firmwide; per-pod small | Per-pod caps U; firmwide netting central (SI) | Gross reported in press as 5–7×+ firmwide (SI/WI — treat with caution) | 2–3 on internals |
| AQR/DFA | 100s–1000s | Tiny per-name; risk at factor level (V, prospectuses) | Long-only funds unlevered; EMN funds levered (V, prospectuses) | 5 |
| Renaissance Medallion | 1000s | U | Reported high leverage via basket options (V that the structure existed — Senate 2014 report on RenTec basket options) | 3 |

## 5.3 The six construction archetypes (required contrast)

1. **Concentrated fundamental** (Berkshire, TCI, PSH): 5–20 names, idiosyncratic risk *embraced*,
   diversification replaced by depth of knowledge + balance-sheet safety. Tolerable only with
   permanent/locked capital (Berkshire's float, PSH's closed-end listing — both structural, both V).
   **The capital structure is part of the portfolio construction.**
2. **Diversified quantitative** (DFA, AQR long-only): breadth is the whole point (Grinold: IR ≈
   IC×√breadth — V academic); no name matters; risk managed at factor level; capacity huge.
3. **Market-neutral** (EMN pods, TOPS-style): dollar/beta/sector/factor-neutral by construction;
   returns purely cross-sectional; leverage mandatory to make residual alpha investable — which
   imports the Aug-2007 unwind fragility (V academic, Khandani–Lo).
4. **Multi-manager platform** (Millennium, Citadel): portfolio construction = *capital allocation
   across PMs* under mechanical de-risking; firm-level book is an emergent object nobody "picked."
   Netting means the firm's gross exposure vastly exceeds any pod's view (SI).
5. **Event-driven** (Third Point, Elliott): position sizes keyed to event probability, downside-
   to-break, and time-to-catalyst; book turns over with the event calendar; cash is a residual.
6. **Long-only institutional** (Contrafund, Capital Group, NBIM): benchmark-relative construction —
   active weights, tracking-error budgets, sector bands. NBIM's 1.25pp expected-relative-vol cap
   (V) is the cleanest published example of an entire portfolio built inside a risk budget.

**No universal method exists** — the assignment's suspicion is confirmed by the evidence: each
archetype's construction follows from its capital structure, liability profile, and edge breadth.
Copying the construction without the capital structure (e.g., 40% single positions without
permanent capital) is the documented Sequoia/Ackman-era failure mode.

## 5.4 Findings for System design (Phase 12)

1. **Max-position caps are the one rule present in every surviving archetype** (even Berkshire's
   concentration was in a company, Apple, that was itself diversified and hyper-liquid — and got
   trimmed). Proposed hypothesis range for Phase 15: 5–10% at cost for a concentrated book,
   1–3% for a diversified one.
2. **Sizing ∝ 1/volatility with liquidity caps** is the most evidence-backed mechanical rule
   (used across systematic shops; survives academic scrutiny; implementable at any scale).
3. **1/N is the honest default.** DeMiguel et al. (V): with realistic estimation error, equal
   weight beats optimization for small position counts. A retail system claiming optimizer alpha
   carries the burden of proof.
4. **De-risking schedules (platform-style) transplant well** because they need no forecasts —
   only P&L accounting. This becomes the backbone of the Phase 15 rulebook.
5. **Fractional Kelly as a ceiling, not a target:** documented survivors size *below* theoretical
   optimum; every documented blowup sized above it (LTCM's own principals later wrote about
   over-betting — V, post-mortem literature).
