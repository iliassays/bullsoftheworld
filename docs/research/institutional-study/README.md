# Institutional Equity Investing — Reverse-Engineering Study

**Assignment:** Discover how genuinely successful hedge funds and institutional investors find,
validate, size, execute, monitor, and exit U.S. equity investments — then distill the strongest,
most repeatable practices a technically capable independent investor could adapt.

**Commissioned:** 2026-07-19. **Execution mode:** phased across sessions.
**Feeds:** the Atlas investment mandate (`docs/research/atlas-investment-mandate.md`) — candidate
practices from this study become preregistered paper experiments, never direct live changes.

## Evidence rules (binding for every phase)

Every important claim carries one of these labels:

- **Verified** — supported by primary evidence (audited reports, regulatory filings, court records)
- **Manager-stated** — claimed by the investor/institution, not independently audited
- **Strongly inferred** — supported by several credible independent observations
- **Weakly inferred** — plausible but incompletely supported
- **Unknown/proprietary** — no credible public information; never guessed at

Evidence-quality score 1–5 (5 = audited/regulatory primary evidence; 1 = marketing/speculation).
Only institutions scoring ≥3 are used as primary case studies. Nothing is fabricated: no invented
returns, entry prices, position sizes, stop levels, or internal limits — "not publicly available"
is the required answer when that is the truth. Hedge-fund performance is mostly self-reported or
press-derived; the study says so wherever it applies rather than laundering it into fact.

## Phase index

| Phase | Content | File | Status |
|---|---|---|---|
| 1 | Candidate universe (30+) + screening table + selections | `phase1-candidate-universe.md` | **done 2026-07-19** |
| 2 | Strategy-family taxonomy (22 families) | `phase2-strategy-families.md` | **done 2026-07-19** (spot-verify academic cites in Phase 16 pass) |
| 3 | Idea generation (fundamental / catalyst / quant / alt-data) | `phase3-idea-generation.md` | **done 2026-07-19** |
| 4 | The institutional decision pipeline | `phase4-decision-pipeline.md` | **done 2026-07-19** |
| 5 | Portfolio construction | `phase5-portfolio-construction.md` | **done 2026-07-19** |
| 6 | Risk management (4 levels) + averaging-down investigation | `phase6-risk-management.md` | **done 2026-07-19** |
| 7 | Entry, execution, exit | `phase7-entry-execution-exit.md` | **done 2026-07-19** (FIM per-trade bps tables unverified — spot-check in Phase 16 pass) |
| 8 | Regulatory-filings workflow (13F et al.) | `phase8-filings-workflow.md` | **done 2026-07-19** (no post-2020 peer-reviewed 13F-cloning re-test found — Phase 16 red-team item) |
| 9 | Detailed case studies (16 institutions) | `phase9-case-studies.md` | **done 2026-07-19** (pod-rule primary hunt empty — documented absence; several ledger IOUs closed/corrected) |
| 10 | Historical trade case studies (30+) | `phase10-trade-cases.md` | **done 2026-07-19** (GGP "$2.6bn" contamination caught; famous-trade P&L frequently U — labeled throughout) |
| 11 | Cross-institution patterns | `phase11-patterns.md` | **done 2026-07-19** (headline: downside-first-by-a-non-author invariant; conditionals table; myth register) |
| 12 | Three practical systems (A/B/C) | `phase12-systems.md` | **done 2026-07-19** (candidates for mandate admission only; 7 rejected systems documented) |
| 13 | Backtesting & validation protocol | `phase13-validation.md` | **done 2026-07-19** (extends mandate steps 1–7; repo commit = preregistration receipt) |
| 14 | Implementation roadmap | `phase14-roadmap.md` | **done 2026-07-19** (EDGAR pipeline = highest-leverage artifact; zero paid data through Stage 2) |
| 15 | Risk rulebook | `phase15-risk-rulebook.md` | **done 2026-07-19** (all numbers = hypotheses w/ ranges; structure is the evidence-backed part) |
| 16 | Red-team + final ranked recommendations | `phase16-redteam-final.md` | pending |

`ledger.md` — running research ledger (claim / source / contradiction / category / confidence /
open uncertainty). Update it in every phase; check it before asserting anything numerical.
