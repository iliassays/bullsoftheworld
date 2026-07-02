# Platform intelligence research — July 2026

Deep-research report for the Bulls of Dhaka strategy: institutional data-intelligence platforms,
2024–2026 retail fintech trends, and Dhaka Stock Exchange analysis. Every claim below survived
adversarial 3-vote verification against live primary sources on 2026-07-02 unless marked otherwise.

## TL;DR

- **The social layer is the moat.** StockTwits (Thematic acquisition, July 2025) and eToro (Alpha
  Portfolios, May 2025) are both betting on proprietary community/behavioral data as the core AI
  asset. A DSE social layer generates sentiment data no incumbent can copy.
- **DSE is data-rich for a frontier market.** dsebd.org freely publishes the exact raw ingredients
  for red-flag, screener, and ownership-tracking features — and BSEC's insider-trading rules hinge
  on *unpublished* information, so analytics over published disclosures sit outside that prohibition.
- **Basic tools are commoditized locally** (AmarStock, StockNow, LankaBD all ship screeners,
  charts, depth). Differentiation = synthesis + social + reliability + fully-free.
- **The regulator's hostility to Facebook stock tips is a tailwind**: position as the verified,
  disclosure-grounded alternative.

## Thread 2 — Trends (strongest verified signal)

### StockTwits → AI on proprietary social data (HIGH confidence, 3-0 ×3)
Acquired AI research startup Thematic (July 2025). Announced Q4 2025 launches: AI-native search,
smart screeners, a **"Social Relative Strength Index"** (community activity + market data), and an
index builder with backtesting — all on 17 years of proprietary data (ticker follows, conversations,
sentiment, behavior patterns). Explicit thesis: community data differentiates their AI from
"sterile" TradFi data. *Caveat: announced direction, not verified-shipped.*
Source: stocktwits.com press announcement, corroborated by Lindzon's blog, Pulse2, Investing.com.

### eToro → retail behavior as alternative data (HIGH confidence, 3-0 ×2)
May 2025: seven ML-driven "Alpha Portfolios" built on anonymized retail trading data from 40M
registered users (their framing; funded accounts ~3.6M). Retail platforms monetizing their own
user-behavior exhaust is *the* 2024–2026 trend. For us: aggregated sentiment/watchlist/flow data
as **descriptive analytics** (never an investment product — no-advice constraint).

## Thread 3 — Dhaka Stock Exchange

### Market structure (HIGH confidence, verified digit-for-digit)
- Total market cap ~BDT 6.98tn (~USD 57bn headline, **~USD 28bn equity-only** excluding listed
  treasury bonds); daily turnover ~BDT 14.4bn (~USD 118mn) across ~327K trades — roughly 0.2% of
  headline cap per day (June 2026 range: BDT 8.3–15.7bn).
- Implications: volume/flow analytics carry outsized signal per trade; **liquidity itself is a
  feature-worthy data point** (thin stocks are manipulation-prone); ad TAM bounded by a modest
  active-trader base.

### Data availability — better than the frontier label suggests (HIGH confidence)
All free public exchange data, live-verified 2026-07-02:
- Delayed-intraday snapshots with explicit as-of timestamps (our production scraper already proves this).
- Structured disclosure datasets: sortable price tables, gainers/losers, **circuit-breaker lists**,
  P/E at a glance, **sectoral median P/E**, a **"Going Concern threat List"**,
  **financial-statement submission status**, marginable securities, AGM/EGM/record dates, data archive.
- LankaBD serves **shareholding-position tables** (sponsor/institute/foreign/public splits, monthly)
  and block transactions as unauthenticated static HTML.
- Caveats: HTML scraping only (no API/CSV), broken TLS chain on dsebd.org, **no explicit
  redistribution license published** (ToS risk unassessed — open question).

### Regulatory environment
- Foundation: Securities and Exchange Ordinance 1969 + BSEC Act 1993. Full regulatory corpus free
  and actively maintained on sec.gov.bd (HIGH confidence).
- **Prohibition of Insider Trading Rules 2022** (gazetted Jan 30, 2023). The prohibition hinges on
  *Unpublished* Price Sensitive Information — analytics built exclusively on already-published
  disclosures fall outside it by definition (MEDIUM confidence, 2-1 vote — an interpretation, not a
  regulator statement; **local counsel review warranted** before scaling commentary features).
  Separate exposure remains: market-manipulation provisions (SEO 1969 s.17) and any analyst/advice
  licensing rules — **not researched**.
- DSE's homepage carries an official Bangla warning (linked to a BSEC notification) telling
  investors not to act on Facebook/unverified tips (HIGH confidence). → Position Bulls of Dhaka as
  the verified, source-linked, moderated anti-Facebook alternative; the regulatory posture becomes
  a tailwind.

### Local competitors (HIGH confidence, all live-verified)
| Platform | Ships | Monetization | Gap |
|---|---|---|---|
| AmarStock | Interactive/MTF charts, 1-min volume-price, depth, 3 screener variants, P/E analytics | Premium tier + paid courses (৳4,999–8,499) | Charting-centric, paywalled depth |
| StockNow | Screener, alerts, portfolio, block trades, halted/spot/SME lists, IPO, multi-chart, education | Free + ads + subscription tier; **100K+ downloads** (~435K installs) | **Chronic trading-hour outages** (white screens, server capacity — medium confidence, user reviews); still rated 4.12/5 |
| LankaBD | Live DSE data incl. Level 2, shareholding positions, block trades, circuit breakers, screener | Brokerage-owned | Institutional-feeling, no social |

**Nobody combines fully-free + social layer + synthesized intelligence.** That's the open position.
StockNow's 100K+ ad-supported downloads prove six-figure demand for a free DSE data app; its
trading-hour outages are a concrete reliability wedge.

## Feature opportunities ranked (synthesis, medium confidence)

**Tier 1 — fully feasible now, all inputs verified public:**
1. **Red-flag composites** — going-concern list + financial-statement submission status +
   circuit-breaker/category + sectoral P/E outliers (matches our roadmap's Red Flags feature)
2. **Ownership-change tracking** — sponsor/director/institute/foreign/public shareholding deltas
   from monthly tables; the retail adaptation of Fintel-style ownership intelligence
   (change detection, sponsor-selling alerts — descriptive narratives)
3. **Block-trade surfacing**
4. **Corporate-calendar intelligence** — AGM/EGM/record dates

**Tier 2 — feasible, differentiating:**
5. Community sentiment as proprietary data (bull/bear tags, ticker follows, an SRS-style
   social-activity index — the StockTwits playbook)
6. AI/LLM disclosure + market-day summaries (descriptive-only)
7. Liquidity / thin-stock warnings

**Tier 3 — blocked by market structure:** real-time flow, options data, short interest
(no short-selling market), tick data.

## Refuted claims (killed in verification — do not rely on)
- "StockNow covers both DSE and CSE with full bilingual analysis" (1-2)
- "StockNow is freemium/subscription rather than ad-supported" (1-2)
- "StockNow's basics are so complete we can't differentiate on them" (0-3)

## Known gaps in this research
1. Thread 1 (Bloomberg/FactSet/Fintel feature catalogs) produced **no surviving verified claims** —
   the feature mapping rests on DSE data availability, not verified platform research.
2. Retail investor base data (BO account counts, demographics) and DSE manipulation/pump-and-dump
   history did not survive verification — unresearched.
3. StockTwits/eToro findings rest on company press releases (announced direction, not shipped).

## Open questions for next steps
1. Does BSEC regulate publication of market commentary/analytics by non-licensed entities
   (research-report rules, adviser licensing, media provisions)? Checkable on sec.gov.bd.
2. DSE's redistribution terms for scraped public data; cost of a licensed feed.
3. Size/activity of the DSE retail base + realistic Bangladesh digital-ad revenue per finance MAU —
   does the ad-only model clear costs at plausible scale?
4. Did StockTwits' Q4 2025 AI tools actually ship and gain traction; which institutional-style
   features have *proven* retail engagement?

---
*Method: 5 search angles → 23 sources fetched → 115 claims extracted → top 25 adversarially
verified (3-vote panels) → 22 confirmed, 3 killed → synthesized. 105 agents. Snapshot date 2026-07-02.*
