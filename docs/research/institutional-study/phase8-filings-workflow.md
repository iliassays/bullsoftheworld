# Phase 8 — The Regulatory-Filings Workflow (13F, 13D/G, Form 4 et al.)

**Date:** 2026-07-19. Labels V/MS/SI/WI/U per Phase 1. Rule mechanics below were verified against
SEC primary sources (the 13F FAQ and the Oct 2023 adopting release were fetched directly) — this
matters because most secondary content online still describes the pre-2024 deadlines. Central
finding up front: **filings are the one institutional information stream retail gets at zero cost
and near-zero lag — and the academic record says exploiting it works only conditionally: the
signal is in *which filers* and *which positions*, never in the aggregate.**

## 8.1 What each filing actually contains (current rules, post-2023/24 amendments)

| Filing | Trigger | Deadline | What it shows / hides | Evidence |
|---|---|---|---|---|
| **13F** | ≥$100M in 13(f) securities (measured on the last trading day of *any* month in the year) | 45 days after quarter-end | Long US-listed equities/ETFs/convertibles/listed options at quarter-end, trade-date basis. **Hides:** shorts (never netted), written options, swaps, bonds, foreign-listed, cash, cost basis, all intraquarter trading | V ([SEC 13F FAQ](https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f)) |
| **13D** | >5% + control intent | **5 business days** (was 10 calendar; effective Feb 2024); amendments 2 business days on material change (1% move deemed material) | Intent, funding, derivative interests incl. cash-settled (Item 6), group members | V ([SEC PR 2023-219](https://www.sec.gov/newsroom/press-releases/2023-219)) |
| **13G** | >5% passive/QII/exempt | Passive initial: **5 business days**; QII/exempt initial: 45 days after quarter-end; all amendments quarterly; 10%-crossing accelerations (QII: 5 bd after month-end; passive: 2 bd) | Passive stakes only; conversion to 13D required if intent changes | V ([Sidley rule summary](https://www.sidley.com/en/insights/newsupdates/2023/10/sec-shortens-filing-deadlines-for-schedules-13d-g)) |
| **Form 4** | Section 16 insiders (officers/directors/>10%) | **2 business days** | Transaction-coded trades: **P** (open-market buy — the signal), S, A (award), M, F, G; 10b5-1 checkbox since 2023 | V ([SEC forms guide](https://www.sec.gov/files/forms-3-4-5.pdf)) |
| **Form 144** | Affiliate resale notice | At/before sale | Electronic on EDGAR only since Apr 2023 — now a machine-readable leading indicator of insider sales | V |
| **N-PORT** | Registered funds, monthly | Only month-3 of each fiscal quarter public, 60 days after quarter-end. **In flux:** 2024 monthly-disclosure amendment delayed 2025, rollback proposed Feb 2026 — re-check before building on it | V ([Sidley](https://www.sidley.com/en/insights/newsupdates/2026/03/us-sec-proposes-to-scale-back-2024-form-n-port-amendments)) |
| **13H** | Large traders | — | **Confidential, FOIA-exempt. No signal available.** | V |

Details that change conclusions:

- **13F options are reported as underlying shares** (PUT/CALL flag in column 5, but share counts
  and CUSIP refer to the underlying — V, SEC FAQ verbatim). A reported "position" may be a hedge
  or a lottery ticket; share counts overstate economic exposure. Any 13F pipeline must treat
  option rows separately or discard them.
- **Net exposure is unknowable from a 13F.** Shorts and written options are never reported and
  never netted (V, FAQ verbatim: short positions "will not be reported... or subtracted from a
  long position in the same issuer"). A fund long stock + long puts looks maximally bullish.
- **Confidential treatment** lets accumulators hide positions for up to ~a year (SI on duration):
  Berkshire–IBM 2011 and Chubb 2023–24 (SI — the CT grant itself is never published with names;
  Chubb is better documented via before/after 13Fs); the SEC has also *denied* Berkshire CT
  (V, 2003 order). Practical consequence: the biggest fish are precisely the ones whose current
  buying you cannot see.
- **The Archegos hole is still open (V, decisive for this study):** proposed Rule 10B-1 (large
  security-based swap position disclosure, Dec 2021) was **formally withdrawn June 12, 2025**
  ([SEC](https://www.sec.gov/rules-regulations/2025/06/position-reporting-large-security-based-swap-positions)).
  The 2023 cash-settled-derivatives *guidance* (not rule) is the only constraint, untested in
  court. An Archegos-style hidden long remains invisible to filing-followers as of mid-2026.
- **Data quality is a real defect, not pedantry:** SEC OIG criticized 13F reliability (2010);
  academic work documents strategic use of restatements/amendments and systematic gaps in the
  Thomson S34 data most studies were built on (SI). Build from EDGAR raw XML, not vendor
  shortcuts, when it matters.
- **The whole pipeline is now machine-readable end-to-end (V):** 13F structured XML since May
  2013 (+ SEC-published quarterly TSV data sets), Form 4 XML since 2003, 13D/G Inline-XBRL since
  Dec 18, 2024, Form 144 electronic since Apr 2023.

## 8.2 Does following filings work? The academic record

### 13D — the strongest documented filing signal

- **Brav–Jiang–Partnoy–Thomas (2008, JF — V):** ~7% abnormal return around activist 13D filings
  (2001–2006), **no reversal in the following year**; ~2/3 of campaigns succeed at least
  partially. **Bebchuk–Brav–Jiang (2015, Columbia L. Rev. — V):** five-year data rejects the
  myopia critique — the initial spike is not reversed. Caveat, honestly labeled: a meaningful
  share of the announcement return accrues in the *pre-filing run-up* the filer buys through
  (that's what Phase 7's 325%-turnover trigger-day finding is); the follower captures only the
  post-filing portion — the split is WI, not quantified in the sources gathered.
- The 2024 deadline compression (10 calendar → 5 business days) mechanically *improves* the
  follower's freshness. Same event, less staleness.

### 13F cloning — works only conditionally, and the disagreement is preserved

| Study | Finding | Cat. |
|---|---|---|
| Martin–Puthenpurackal 2008 | Mimicking Berkshire's disclosed holdings *the month after disclosure* earned significant positive alpha (~+10.75%/yr vs S&P; a +14.26% abnormal figure also circulates — two specifications, not reconciled; direction robust) | V paper / SI exact magnitude |
| Cohen–Polk–Silli "Best Ideas" | Managers' most-overweighted positions beat the market ~2.8–4.5%/yr; **the rest of their portfolios show nothing** | V |
| Verbeek–Wang 2013; Frank–Poterba–Shackelford–Shoven 2004 | Copycat funds ≈ or marginally beat the originals net of costs, despite the lag | V |
| Farouk–Jivraj 2020 (working paper) | Systematic 13F manager-selection beat S&P by ~3.8%/yr 2004–2019; cloned alpha decays over ~12 months — the 45-day lag is survivable for low-turnover signals | SI (not peer-reviewed) |
| **Griffin–Xu 2009 (RFS) — the counter-evidence** | Hedge-fund 13F holdings 1980–2004 in aggregate show essentially **no** cross-sectional predictive ability; the slight edge vanishes equal-weighted and is a 1999–2000 artifact | V |

**Reconciliation (SI, ours):** selection is the whole strategy. Conviction-weighted top holdings
of concentrated, low-turnover, single-CIO managers carry signal; the aggregate universe carries
none; multi-strategy platforms are definitionally noise (Millennium's single 13F aggregates 330+
independent pods with offsetting books and invisible shorts — SI/WI). No post-2020 peer-reviewed
re-test was located — flagged for the Phase 16 red-team rather than assumed away.

### Form 4 — buys signal, sales don't, and *who* is buying matters most

- **Lakonishok–Lee (2001, RFS — V):** purchases informative, sales not; power concentrated in
  small firms. This asymmetry is structural: sales have a hundred innocent reasons, open-market
  buys (code P) have one.
- **Cohen–Malloy–Pomorski (2012, JF — V), the load-bearing refinement:** split insiders into
  **routine** (same month every year — >50% of all insider trades, signal ≈ zero) and
  **opportunistic**; opportunistic trades earn ~82 bps/month value-weighted abnormal and predict
  firm news. The filter is computable from filing history alone — pure free data.
- **Cluster buying** (several insiders buying in a window) beats single buys — vendor-stated
  magnitudes (2iQ: ~3.8% vs ~2% at 21 days — MS, commercial source); academic anchor cited
  secondhand only (SI). Direction credible, numbers not to be relied on.
- **Timing dispute, preserved:** the classic drift results predate modern filing speed; one
  practitioner-academic summary argues most insider alpha is now impounded within days of the
  2-business-day filing (WI, single source). Post-2023 the 10b5-1 checkbox lets a follower
  discard pre-scheduled trades — a free signal-cleaner the classic studies didn't have.
- **10b5-1 reform (Dec 2022 — V):** cooling-off periods (90–120 days for officers/directors),
  overlapping-plan ban, good-faith certification. Net effect: scheduled sales are cleaner
  labeled, and *non*-plan trades are a purer discretionary signal than in any historical sample.

### Decay

McLean–Pontiff's ~30–50% post-publication decay (Phase 3) applies to disclosure-based signals as
to any other. No located study shows best-ideas-style cloning at zero yet (SI, thin — strongest
recent evidence is the 2020 working paper). Plan at half the historical magnitudes.

## 8.3 The practical workflow (all free; endpoints verified live this pass)

1. **Ingestion — EDGAR direct, no key, 10 req/s with a declared User-Agent** (V, endpoints
   returned 200 this pass; generic clients get 403'd — set a real UA string):
   - Full-text search API (filings since 2001): `efts.sec.gov/LATEST/search-index?q=...`
   - Per-filer submissions: `data.sec.gov/submissions/CIK##########.json`
   - Daily index files for the polling loop: `sec.gov/Archives/edgar/daily-index/`
   - Quarterly 13F TSV extracts: SEC "Form 13F Data Sets" page
2. **Watchlists, per the evidence:**
   - **13D stream** — event signal, act on filing day (the drift doesn't reverse; freshness now
     ≤5 business days). Track named activists with documented records (Elliott, Third Point,
     Pershing — Phase 1 tier).
   - **13F clone list** — concentrated, low-turnover, single-CIO filers only; clone **top-5
     overweights**, never whole portfolios (Best Ideas); discard option rows or handle
     separately; skip anything platform-shaped.
   - **Form 4 stream** — code-P open-market buys only; drop 10b5-1-checked trades; compute
     routine-vs-opportunistic from each insider's own filing history (CMP filter); weight
     clusters over singletons; expect the edge in small caps (where Phase 7's spread-cost
     warning applies — the two findings collide and Phase 12 must price that collision).
3. **Hygiene rules (each grounded in §8.1):** treat every 13F position as 45–135 days stale and
   possibly already exited; never infer net exposure; expect window dressing in quarter-end
   snapshots (V academic — Agarwal–Gay–Ling: losers window-dress more, worst at fiscal year-end);
   process amendments/restatements; dedupe multiple CIKs per firm; filter out index/custody
   filers before computing "institutional ownership."
4. **Legal position (SI, uncontroversial):** trading on public filings is legal — the filings
   are public by definition; the follower has no filing duty until they themselves cross 5% or
   become an insider. The enforcement risk runs entirely the other way (the SEC's 2024 sweep hit
   *late filers*, not readers).

## 8.4 Findings for Phase 12/15

1. **The 13D event stream is the highest-grade free signal in the study so far:** peer-reviewed,
   non-reversing, recently *improved* by regulation, and executable at retail size (Phase 7's
   advantage) on filing day. Candidate for a preregistered paper experiment under the Atlas
   mandate.
2. **13F cloning is a manager-selection problem wearing a data costume.** The evidence supports
   exactly one recipe: top-conviction overweights of a hand-curated list of concentrated
   low-turnover managers, refreshed quarterly, decaying over ~12 months. Everything else in a
   13F is noise or worse.
3. **Form 4's free-data refinements stack:** P-codes only → drop 10b5-1 plans → routine/
   opportunistic filter → cluster weighting. Each step is computable from EDGAR alone. The open
   question (modern-era decay) is testable in-house before committing capital — a Phase 13 job.
4. **Know what the stream cannot show:** current accumulation by CT users, all short exposure,
   all swap exposure (10B-1 withdrawn), anything intraquarter (institutions provably earn
   intra-quarter profits the snapshot misses — Puckett–Yan, Phase 7). Filings describe the
   visible portion of the iceberg; Phase 12 systems must never treat them as the whole.
5. **Cross-reference for the squeeze/holder work:** the fingerprint research elsewhere in the
   portfolio (which-funds-hold-it questions) inherits §8.1's caveats wholesale — especially
   options-as-underlying-shares and index/custody-filer pollution.
