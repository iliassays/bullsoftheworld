# Phase 3 — How Institutions Generate Ideas

**Date:** 2026-07-19. Evidence labels as in Phase 1 (V/MS/SI/WI/U). New verified sources added to
`ledger.md`. Overriding finding up front: **idea generation is the least differentiated stage of
the institutional pipeline.** The inputs below are mostly shared; Phases 4–7 (validation, sizing,
risk, execution) are where the documented survivors actually separated from the failures.

## 3.1 Fundamental methods

How the Phase 1 fundamental institutions actually source ideas, per their own letters and filings:

- **Coverage + patience, not eureka screens.** Berkshire (V, shareholder letters): read widely for
  decades, act rarely, inside a declared circle of competence; ideas are recognized, not generated.
  Contrafund/Danoff (MS, interviews): meet extreme numbers of companies; ideas emerge from
  comparative context ("best-of-breed" selection within known industries).
- **Quality-of-earnings work is the fundamental analyst's actual edge claim.** The checks that
  recur in documented processes: cash conversion (FCF vs reported earnings), accrual levels
  (Sloan 1996 accrual anomaly — V academic), revenue-recognition aggressiveness, serial
  "one-time" charges, receivables/inventory growing faster than sales, capitalized costs.
  Greenlight's short theses (MS, letters — e.g., the 2002 Allied Capital and 2008 Lehman calls,
  both later vindicated publicly — V outcome) were built almost entirely on this toolkit.
- **Unit economics / industry structure:** TCI (MS, letters + II profile): "sustainable competitive
  moats with pricing power, high barriers, predictable cash flows" — infrastructure-like equities.
  This maps directly onto Porter-framework work every analyst is trained on; nothing proprietary
  about the framework, only the judgment.
- **Valuation methods in documented use:** DCF/scenario ranges (PSH annual reports show per-thesis
  scenario framing — V that they publish it, MS the numbers), sum-of-the-parts for conglomerate/
  activist targets (Elliott, Third Point letters — MS), private-market value for take-private
  candidates. **Not documented anywhere credible:** a valuation formula that itself constitutes
  the edge. The recurring documented pattern is conservative inputs + insistence on a discount,
  not a better formula.
- **Management/capital-allocation assessment:** universally claimed (MS across all letters),
  unverifiable as a repeatable method. Treat as judgment, not process.

**Retail access:** every input above is public (filings, transcripts, industry data). The gap is
hours-per-name and management access — which matters least in small/neglected names (consistent
with Phase 2 finding #1).

## 3.2 Estimate & catalyst methods

- **Earnings surprise / PEAD:** the classic anomaly (Bernard–Thomas 1989 — V academic). **Live
  contradiction, recorded honestly:** Martineau (2022, "Rest in Peace Post-Earnings Announcement
  Drift" — V academic) finds PEAD gone from non-microcaps by ~2006, while other 2021–2024 studies
  still find exploitable drift, mostly in smaller/low-attention names. Working conclusion for
  Phase 12: PEAD survives, if at all, in small/low-coverage stocks — exactly where execution costs
  bite. Do not build a system that needs large-cap PEAD.
- **Analyst estimate revisions:** revisions momentum is among the more robust catalyst signals
  (Chan–Jegadeesh–Lakonishok 1996 — V academic) and is a stated core input at systematic L/S shops
  (Marshall Wace's origin story is broker-signal aggregation via its TOPS system — SI, widely
  reported). Point-in-time estimate data (IBES-style) is expensive; this gates retail replication.
- **Corporate events, ranked by remaining evidence strength (SI synthesis):**
  1. **Spin-offs / forced-seller events** — decayed but structurally rooted (index funds and
     mandates must sell what they receive); still the best retail-accessible catalyst family
     (Phase 2 §16).
  2. **Post-bankruptcy equities, thin-coverage relistings** — neglect-driven; episodic.
  3. **Buyback + insider-buying combinations** — modest academic support (share-issuance factor
     works in reverse — V academic, Fama–French issuance results).
  4. **Index inclusion** — effect decayed toward zero post-2010 (V academic, multiple studies);
     institutions now trade the *crowding around* it. Retail: avoid, don't play.
  5. **Merger closes** — Phase 2 §13; thin spreads, leverage-dependent.
- **Guidance changes / investor days / regulatory decisions:** event-driven funds' bread and
  butter (Third Point letters — MS), but these are timing devices layered on a fundamental thesis,
  not standalone signals.

## 3.3 Quantitative methods

Mapping the assignment's factor list to evidence (all V academic unless noted):

| Signal | Evidence anchor | Post-publication status (McLean–Pontiff 2016 framework) |
|---|---|---|
| Value (multiple defs) | Fama–French 1992/2015 | Survived a brutal 2017–20 drought; positive since (AQR 2021–23, Phase 1) |
| Momentum 3–12m | Jegadeesh–Titman 1993 | Robust OOS; crash-prone (2009) |
| Quality/profitability | Novy-Marx 2013; AFP QMJ 2019 | Holding up |
| Low volatility/beta | Frazzini–Pedersen BAB 2014 | Contested (leverage constraints vs data choices) |
| Accruals | Sloan 1996 | Substantially decayed in large caps (SI, follow-up lit.) |
| Share issuance | Fama–French | Holding up |
| Short-term reversal | Lehmann 1990 | Gross-only; cost-eaten (Phase 2 §11) |
| Long-term reversal | DeBondt–Thaler 1985 | Weak/subsumed by value |
| Seasonality | Heston–Sadka 2008 | Fragile; treat as WI |
| Insider activity (Form 4) | Multiple studies: purchases predictive, sales not | Modest but persistent; free data |
| **ML models** | Gu–Kelly–Xiu 2020: ML improves cross-sectional prediction | Improvement concentrated in microcaps/high-cost names (their own robustness checks) — implementability is the open question |

**Institutional practice vs retail practice:** the institutions (AQR, DFA — V via funds) win on
*implementation*: netting trades across signals, patient execution, tax/cost engineering — not on
secret factors. McLean–Pontiff's ~30–50% post-publication decay (V academic) is the planning
number for any Phase 12 system.

## 3.4 Alternative data — source-by-source assessment

Market context (SI, industry estimates — treat magnitudes, not decimals): alt-data market ~$12bn
(2025); large funds spend $1M per $1bn AUM ramping to ~$3M/yr (Morgan Stanley estimate via press);
top-20 funds ~$40–60M/yr each. **Legality landmark (V):** SEC v. App Annie (Sept 2021, first
alt-data enforcement) — $10M penalty for misrepresenting that confidential app-store data was
excluded from sold estimates. Lesson: data *provenance* is a compliance surface, and funds now
diligence providers accordingly.

| Source | Legality/compliance | Cost (SI, press ranges) | Hist. depth | Point-in-time quality | Leakage/priced-in risk | Retail access |
|---|---|---|---|---|---|---|
| Credit-card panels | Legal if properly anonymized/consented; panel-bias disclosure matters post-App Annie | $100k–$1M+/yr | ~10–15 yr | Vendor-restated panels are a real backtest trap | High priced-in risk for mega-caps (many buyers) | **No** (cost) |
| Web traffic (Similarweb-class) | Legal | $10k–$100k+/yr | ~10 yr | Methodology changes break history | Medium | Partial (degraded free tiers) |
| App downloads/usage | Legal post-App-Annie cleanup | $10k–$100k+ | ~12 yr | See App Annie case — provenance risk | Medium-high | Partial |
| Job postings | Legal (public postings) | $0–$50k | ~10 yr | Site coverage shifts | Low-medium | **Yes** (scrapeable/free tiers) |
| Employee reviews (Glassdoor-class) | Legal; ToS constraints on scraping | Low | ~15 yr | Review-bombing noise | Low | **Yes** |
| Satellite imagery (parking lots, storage tanks) | Legal | $50k–$500k+ | ~10–15 yr | Weather/methodology noise | Documented academic result: satellite parking signals predicted retailer earnings AND their informational advantage decayed as adoption spread (Zhu/Katona et al. — V academic) | **No** |
| Shipping/logistics (AIS, bills of lading) | Legal (public AIS; import records FOIA-derived) | $10k–$100k | 10–20 yr | Good | Low-medium for small caps | Partial |
| Pricing scrapes (e-commerce) | Gray: hiQ v. LinkedIn narrowed CFAA scraping risk for public data (V, 9th Cir.), but ToS/contract claims remain live | Variable | Short | Fragile collection | Medium | **Yes** at small scale |
| Search trends | Legal, free (Google Trends) | $0 | ~20 yr | Index renormalization is a leakage trap | High for obvious tickers | **Yes** |
| Social sentiment | Legal; API costs rose sharply post-2023 | $0–$100k | ~15 yr | Bot contamination; survivor platforms | High and reflexive (WSB is now a crowding *indicator* — Melvin case, Phase 1) | Partial |
| Patents/gov contracts (USPTO, USAspending, FPDS) | Legal, free, official | $0 | Deep | Excellent (official timestamps) | Low (under-used) | **Yes** |
| Geolocation/foot traffic | **Highest compliance risk**: FTC actions against location brokers (Kochava suit, X-Mode/InMarket bans 2024 — V) | $50k–$500k | ~8 yr | Panel drift | Medium | **No** (and shouldn't) |
| **Expert networks** | Legal as a *format*; the documented catastrophic failure mode is MNPI transmission — Galleon/Rajaratnam (11-yr sentence, $20M+ illicit profits) and Primary Global prosecutions (V, DOJ/SEC) | $1k+/call | n/a | n/a | n/a | **No** — and the compliance burden is the point |

**Alt-data verdict for Phase 12:** the retail-viable subset is the free/official tier (job
postings, gov contracts, patents, search trends, reviews, small-scale price scrapes) used as
*thesis evidence*, not as standalone signals. Paid panels are institutionally arbitraged in large
caps before retail could act anyway (the satellite-data decay study is the documented proof that
alt-data edges are adoption-decaying).

## 3.5 Synthesis — where idea-edge actually lives (feeds Phases 11–12)

1. **Shared inputs, differentiated filters.** Everyone reads the same filings and screens the same
   factors. The documented survivors add a *disqualification* layer (Phase 4) that kills most
   candidates; the documented failures (Tiger 2022 growth basket) shared each other's ideas
   without independent kill-criteria — crowding as idea-generation pathology.
2. **For a small operator, the evidence supports three idea engines:** (a) systematic factor
   ranking on the big-four premia (cheap, replicable, decayed-but-alive); (b) forced-seller /
   neglect events (spin-offs, post-bankruptcy, small-cap disclosure lag); (c) quality-of-earnings
   screening as a *negative* filter (avoid the Valeants before they detonate — Sequoia control
   case). All three run on free or cheap data with official timestamps.
3. **What not to build:** anything whose edge claim is faster consumption of widely-sold data.
   That race is documented (satellite decay study, alt-data spend arms race) and lost by
   construction at retail scale.
