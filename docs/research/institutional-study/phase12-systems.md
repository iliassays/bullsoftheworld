# Phase 12 — Three Practical Systems (A/B/C)

**Date:** 2026-07-19. Labels V/MS/SI/WI/U per Phase 1. **Governance framing (binding):** these are
*candidate hypotheses*, not validated strategies. Each enters through the Atlas mandate's
admission process (economic thesis → immutable spec → data audit → historical diagnostic →
forward shadow → promotion gates) as a preregistered paper experiment; none may touch live
capital by virtue of appearing in this study. Per the mandate: no strategy is preferable to a
misleading strategy, and abstention is a result. These designs are US-market-shaped (that is what
the evidence base covers); any DSE transposition needs its own data audit — the DSE bounded
portfolio (max 3 shadow books) is not modified by this document.

Design constraints inherited from Phase 11.E, applied to all three systems:
- **Named structural asset** (else the system is assumed edgeless).
- **Conjunction-breaker:** at least one of {concentration, leverage, illiquidity, crowding}
  hard-capped at zero or near-zero at all times.
- **Pre-commitment medium:** the spec lives in the repo, versioned; breaches are logged events.
- **Costs modeled at Patton–Weller pessimism** (tens of bps one-way in small caps), decay
  haircut ~50% of published anomaly magnitudes (McLean–Pontiff).
- **Null models:** cap-weighted index and 1/N. A system that can't beat both after costs parks.

## System A — Filings-event follower ("the 13D book")

- **Economic thesis (who is forced/slow/biased):** activist stake disclosure compresses months of
  private research into one public event; the post-filing drift is peer-reviewed and does not
  reverse (Brav et al. 2008; Bebchuk–Brav–Jiang 2015 — V, Phase 8). Large holders *cannot* act on
  the event at retail speed without moving price; retail can (Phase 7's structural asset).
  Secondary sleeve: opportunistic (non-routine) insider cluster buys (Cohen–Malloy–Pomorski —
  V; cluster magnitudes MS-only, Phase 8).
- **Universe:** US-listed equities above a hard liquidity floor (spread-based tradeable gate, not
  price-action-based); market cap floor to exclude the spread-eats-everything tier.
- **Signal:** (1) new 13D by a curated activist list (documented multi-campaign records — the
  Phase 1/9 tier: Elliott, Third Point, Pershing, ValueAct-class); entry at next observable
  price after filing dissemination. (2) Form 4 code-P clusters, 10b5-1-checked trades excluded,
  routine insiders excluded by their own filing history.
- **Sizing:** equal-weight per event (1/N inside the book — DeMiguel), position cap 5% of book at
  cost; book cap ~20 concurrent events.
- **Exit (pre-registered, trigger-type sets speed per Phase 7):** campaign resolution / 13D→13G
  conversion / activist exit filing = staged exit; thesis-break (campaign abandoned, delisting
  risk) = immediate; hard time stop at 12 months (the documented drift horizon; Farouk–Jivraj
  decay — SI).
- **Structural asset:** zero market impact at filing-time entry; no career risk holding through
  campaign noise.
- **Conjunction-breaker:** zero leverage; crowding capped by construction (each position is
  *deliberately* co-invested with one large holder — so short interest and borrow data screened
  at entry; no entry into >20% SI names).
- **Evidence against / kill criteria:** pre-filing run-up captures part of the documented return
  (WI split — the experiment measures the follower-capturable share; if it's ~zero after costs,
  kill); no post-2020 peer-reviewed re-test exists (Phase 8 — this book IS the re-test);
  insider-sleeve alpha may be gone at modern filing speed (disputed — measured separately,
  killed separately).

## System B — Forced-seller event book ("the spin-off book")

- **Economic thesis:** index funds and mandate-constrained holders must sell what they receive
  regardless of price (spin-offs, post-bankruptcy distributions, index deletions) — the seller's
  reason is *structural*, not informational. The oldest still-breathing retail-accessible
  anomaly family (Phase 3 ranking #1; Cusatis–Miles–Woolridge — V; Greenblatt/Marriott and
  Ackman/GGP as trade-level exhibits — Phase 10).
- **Universe:** completed US spin-offs/post-emergence equities/forced distributions, 3–24 months
  post-event; same tradeable gate as System A.
- **Signal:** event calendar (corporate actions — free/official data with timestamps), plus a
  *disqualification* layer per Phase 4: leverage flags, going-concern flags, quality-of-earnings
  negative filter (Phase 3's toolkit). No variant perception articulable in writing → no
  position (Phase 4's working rule).
- **Sizing:** 1/N, 5% cap, ~10–15 concurrent; the book accepts long idle periods (event supply
  is episodic — the mandate's anti-entertainment rule applies: no signals is a valid state).
- **Exit:** valuation-normalization target set at entry (staged); thesis-break immediate; time
  stop 24 months.
- **Structural asset:** patience without redemption risk — the documented institutional seller
  *cannot* wait; retail can.
- **Conjunction-breaker:** zero leverage, zero shorting; illiquidity bounded by the tradeable
  gate and 1-day-exit sizing (Phase 7).
- **Evidence against / kill criteria:** the anomaly is decayed (SI) and episodic; if 3 years of
  forward paper evidence shows the disqualification layer doesn't separate outcomes, the book is
  a small-cap value proxy and should be merged into System C or killed.

## System C — Boring factor sleeve with a platform risk grammar ("the ballast book")

- **Economic thesis:** the big-four premia (value, momentum, quality, low-issuance) survive
  publication at ~half magnitude (McLean–Pontiff — V), survive real trading costs at
  institutional scale per the *optimistic* live-data view (FIM — V paper, disputed by
  Patton–Weller — preserved), and are the only return source in this study with 50+ years of
  evidence. Nobody is forced — this is risk-premia harvesting, honestly labeled beta-plus, and
  its null (an index fund) is nearly unbeatable. That is the point: this book exists to
  *measure* whether any active implementation of ours beats the null, and to carry the
  platform-style risk grammar that Systems A/B inherit.
- **Universe/signal:** liquid US equities; composite rank on the four premia; refresh monthly;
  turnover budgeted (the premia's documented cost-survival depends on patient implementation —
  DFA's Keim result is an execution finding, not a signal finding).
- **Sizing:** vol-scaled (∝1/σ) within 1/N bands (Phase 5's two most evidence-backed rules
  combined), ~30–50 names, 3% cap.
- **The risk grammar (the actual product of this book — transplanted platform structure,
  Phase 5/6, folklore-labeled):** drawdown ladder on *each* book: -X% from book HWM → halve
  gross; -1.5X% → flatten and freeze pending written review. X proposed per-book in Phase 15
  with conservative/moderate/aggressive ranges — a *hypothesis*, never an institutional fact
  (no primary source exists — Phase 9). The ladder needs no forecasts, only P&L accounting —
  which is why it transplants (Phase 5 finding 4).
- **Structural asset:** none claimed for the signal (honest); the asset is behavioral — the
  ladder plus automation removes the operator's moment-of-temptation discretion (the
  Druckenmiller-2000 / behavior-gap countermeasure, Phase 11.A.5/C.3).
- **Kill criteria:** if after costs and the decay haircut the sleeve trails both nulls over the
  full preregistered window, it parks permanently and the ladder grammar migrates to whatever
  survives.

## 12.4 What was deliberately NOT built (and why — each rejection cites evidence)

| Rejected system | Reason |
|---|---|
| Large-cap PEAD | Dead in non-microcaps (Martineau — Phase 3's preserved dispute resolves against building on it) |
| Short book of any kind | VW/GME float mechanics (Phase 10); duration economics (5–7yr paybacks — MBIA/Allied); retail has none of the preconditions in Phase 11.B |
| Alt-data speed race | Documented adoption-decay (satellite study) + priced-in-before-retail (Phase 3 verdict) |
| Index-inclusion trading | Effect decayed toward zero post-2010 (V — Phase 3) |
| 13F whole-portfolio cloning | Griffin–Xu (V); only best-ideas-of-curated-filers survives evidence, which System A partially embodies |
| Discretionary macro overlay | Every documented practitioner edge here is MS-tier and non-replicable (Phase 1 evidence-quality screen) |
| Intraday momentum/scalping | Outside this study's evidence base entirely; nothing in Phases 1–11 supports it at retail cost structures |

## 12.5 Portfolio of experiments (the honest summary)

Three books, one shared risk grammar, all paper, all preregistered, each with named kill
criteria and its own benchmark. Expected outcome per the study's own evidence: **at least one of
the three should fail its forward test** — the audited tier's returns are modest (Phase 1), the
decay haircut is real, and if all three "succeed" the first suspect is the validation protocol
(Phase 13), not the market. The Danoff/NBIM benchmarks (+2.9pp/+0.24pp relative) define what
exceptional looks like; the systems' promotion bars are set below that and above the nulls.
