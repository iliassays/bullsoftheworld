# Phase 6 — Institutional Risk Management

**Date:** 2026-07-19. Labels V/MS/SI/WI/U per Phase 1. This phase leans deliberately on the
failure record — the only place internal risk limits reliably become public is the autopsy.

## Level 1 — Individual-position risk

- **Price stops vs thesis stops — a real doctrinal split, documented on both sides.**
  Platforms/quants: hard price/P&L stops, mechanically enforced (SI). Fundamental value shops
  *reject* price stops on principle — a falling price with an intact thesis is an improvement in
  expected return (MS: Klarman, Buffett letters). The split is resolved by what each can afford:
  thesis stops are survivable only with (a) pre-modeled downside, (b) no leverage, (c) permanent
  capital. Absent all three, the platform doctrine is the defensible one. **This conditional is
  the single most important risk conclusion of the study so far.**
- **Earnings-event limits:** pods reduce/flatten into binary events or cap per-event loss (SI,
  consistent secondary descriptions). Fundamental shops hold through. Retail translation: treat
  earnings as a sizing input, not a trading opportunity, unless the thesis IS the event.
- **Short-specific controls (post-GME the documented standard):** cap short interest as % of
  float, monitor borrow fee and utilization, size shorts smaller than longs, prefer defined-risk
  structures. Melvin (V: -53% in one month) is the permanent exhibit: >100% aggregate short
  interest in GME was *public* data before January 2021.
- **Options-defined risk:** PSH's episodic use is the documented gold standard — Feb 2020 CDS:
  ~$27M premium → ~$2.6bn (V, PSH 2020 AR); 2022 rates options similarly (V, ARs). Note both were
  *specific identified risks bought cheaply*, not standing hedges — the distinction Phase 7 keeps.
- **Liquidity limit at position level:** days-to-exit at ≤20–25% of ADV is the standard grammar
  (SI institutionally; V at NBIM which publishes liquidity-risk frameworks). Archegos is the
  negative print (V).

## Level 2 — Portfolio risk

- **Drawdown limits with pre-committed responses** — the platform innovation (Phase 5 §5.1):
  losses mechanically shrink the book. Contrast documented: funds holding through 2022 with no
  de-risking rule took -42% to -67% (Lone Pine, Tiger — Phase 1).
- **VaR/ES and its documented failure:** LTCM ran sophisticated VaR; 1998 correlations went to 1
  across "independent" spread trades and the model's diversification vanished (V, President's
  Working Group report 1999). Institutional practice since: VaR for daily housekeeping, *scenario
  stress tests* (named historical + hypothetical) for sizing the tail (SI, standard practice;
  V at banks via regulation). Rule for Phase 15: size to scenario loss, report VaR, trust neither.
- **Factor concentration:** the 2007 quant quake (V academic, Khandani–Lo 2011) and Tiger 2022
  both show portfolios diversified by name and concentrated by factor. Any book must be viewed
  through a factor lens even if constructed fundamentally.
- **Gross/net exposure caps:** typical documented ranges for L/S equity: gross 130–200%, net
  20–80% (MS across letters; varies). Platforms run far higher gross with netting (SI) — enabled
  by central risk that a single book lacks; do not copy the number without the apparatus.
- **Liquidity mismatch:** the 2008 lesson — funds offering monthly liquidity against level-3
  assets gated or side-pocketed (V, widely documented); Baupost's endowment-style LP base and
  PSH's permanent listed capital are the structural fixes (V). Retail translation: your "redemption
  risk" is your own behavior; a written IPS is the retail gate.

## Level 3 — Manager & strategy risk

- **Capital allocation across PMs/strategies:** platform model (SI): allocations follow realized
  Sharpe and capacity, cut fast on drawdown (-5% halves, -7.5% terminates at Millennium — SI,
  multiple consistent secondary sources, no primary; ~15–20%/yr PM turnover — SI). Independent
  risk teams with veto power are universal at surviving multi-PM firms (SI) and absent in the
  failure record (Archegos: none; Amaranth: overridden — V).
- **Style drift:** documented detector is factor-exposure monitoring vs mandate (V methodologically).
  Amaranth is the canonical drift case: "multi-strategy" fund became a single nat-gas bet (V,
  Senate PSI).
- **Compensation:** platform pass-through + netting-risk structures pay PMs on own-book P&L with
  firm-level clawback/termination — incentives aligned to loss-avoidance (SI). Single-manager
  funds have no such symmetry; the 2015–18 records of even honest concentrated managers show the
  cost of nobody-can-fire-the-founder (Phase 1).

## Level 4 — Firm-level risk

- **Counterparty/PB diversification:** Lehman 2008 — funds with assets rehypothecated at Lehman
  Brothers International Europe lost access for years (V, bankruptcy record). Standard since:
  multiple primes, tri-party custody for excess margin (SI/V via industry documentation).
- **Financing-term risk:** LTCM's one genuinely good practice — long-term locked financing —
  delayed its collapse (V, PWG report); Archegos shows the reverse: same-day margin calls from
  five banks simultaneously (V, court records + [Credit Suisse's own published Archegos
  post-mortem](https://www.sec.gov/Archives/edgar/data/1159510/000137036822000019/cs-20211231.htm) —
  the Paul Weiss report, one of the best free risk-management documents in existence).
- **Model/operational risk:** Two Sigma 2025 SEC order (V, Phase 1) — unsupervised model changes;
  Knight Capital 2012 — $440M in 45 minutes from a deployment error (V, SEC order). Phase 15
  imports both: change control + kill switches are risk management, not IT hygiene.
- **Key-person risk:** universal at founder funds (V by structure); the documented mitigation is
  Berkshire's decades-long succession planning (V, letters/2025 transition) — note it took 50
  years and is the exception.

## Special investigation — when a position moves against the fund

The decision menu (exit / reduce / hedge / hold / add / wait for catalyst / replace) is governed,
in every documented survivor, by **one question asked in a specific order: has the thesis changed,
and would we buy this today at this price as a new position?** Price action alone answers nothing;
but breach of a *pre-committed* risk boundary overrides even an intact thesis.

### Disciplined averaging down — documented examples

| Case | Evidence | Why it qualifies |
|---|---|---|
| Buffett — American Express, 1964 salad-oil scandal | V (historical record; ~40% of partnership capital deployed INTO the scandal) | Thesis (card/traveler-check franchise) untouched by the loss event; downside pre-modeled; no leverage; note it *concentrated* but within stated partnership rules |
| Berkshire — OXY adds on weakness 2022–24 | V (13F/13D filings show adds on price declines) | Pre-declared intent (regulatory clearance to buy up to 50%), unlevered, sized within a giant liquid book |
| Yale — rebalancing into the 2009 trough | V/MS (policy-portfolio discipline per reports + Swensen's book) | Mechanical rebalancing to policy weights = institutionalized buying of declines, pre-committed in writing |
| AQR — holding/adding value exposure 2018–20 | V/SI (Phase 1 record) | Borderline case, honestly labeled: the add intensified pain for two more years; vindicated 2021–23. Qualifies only because the "position" was a diversified factor with 50+ years of evidence, sized to survive being wrong for years — and it barely did (fund shrank ~92% from peak AUM — V, Bloomberg) |

### Undisciplined averaging down — documented examples

| Case | Evidence | The tell |
|---|---|---|
| Ackman — Valeant 2015–17 | V: avg cost ~$166–196, doubled down during decline, exited at ~$11, **>$4bn loss** ([Forbes](https://www.forbes.com/sites/nathanvardi/2017/03/13/billionaire-bill-ackman-sells-disastrous-valeant-investment-after-nearly-4-billion-loss/)) | Thesis mutated repeatedly (platform value → misunderstood accounting → fixable governance); adds based on price, not new information |
| Bill Miller — financials 2008 | V: audited fund; 15-yr streak then fund lost ~2/3 averaging into Bear/AIG/Freddie ([Money](https://money.com/bill-miller-fund-manager-legg-mason-fired/)) | "Lowest average cost wins" stated as doctrine; solvency risk (equity value could be zero) treated as valuation opportunity |
| Sequoia — Valeant 2015–16 | V: filings + board dissent record | Added into decline while position was already >20%; governance objection overridden; dissenters resigned |
| LTCM — 1998 | V (PWG report) | Doubled spread positions as they widened while equity shrank — averaging down *with leverage*, converting drawdown into insolvency |
| Melvin — GME Jan 2021 | V (outcome); position management details partly U | Maintained/pressed a short into a documented squeeze setup; risk boundary (borrow, float) breached before exit |

### The distinguishing test (each item documented in at least one case above)

Disciplined adds require ALL of: (1) original thesis intact and specifically re-verified against
the new information causing the decline; (2) downside was modeled before entry and the current
price is inside that model; (3) post-add position within pre-set caps; (4) no leverage-driven
forced-exit path; (5) adding was contemplated in the entry plan; (6) liquidity permits exit if
wrong; (7) the answer to "new position today?" is yes *in writing, reviewed by someone who didn't
originate the idea* (the Phase 4 invariant again). Undisciplined averaging shows the same five
tells across all documented cases: thesis mutation, price-only justification, cap breach, leverage,
and emotional recovery-seeking (Miller's and Ackman's own retrospectives admit versions of this —
MS, interviews).

## Phase 15 seeds (risk rulebook hypotheses)

Position: max % at cost, vol-scaled sizing, ADV-based liquidity cap, short-squeeze screens,
earnings-event sizing. Portfolio: scenario-loss budget, factor-lens review, gross/net caps,
drawdown ladder (warn → halve → stop) copied structurally from the platform grammar. Process:
pre-registered invalidation + independent-reviewer rule + written re-underwriting before any add
to a loser. Firm/ops: change control, kill switch, broker redundancy. Numbers proposed in Phase 15
as hypotheses with conservative/moderate/aggressive ranges — never as institutional facts.
