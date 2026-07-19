# Phase 7 — Entry, Execution, Exit

**Date:** 2026-07-19. Labels V/MS/SI/WI/U per Phase 1. This phase closes the IOUs from Phase 4
(steps 18–19, 24) and keeps Phase 6's distinction (hedges as *bought-cheaply-against-specific-risks*,
never standing programs). Central finding up front: **execution is the one stage where the retail
investor holds a genuine structural advantage — zero market impact — and exit discipline is the
single most documented separator between the survivors and the failures.** The entry side is where
institutions spend fortunes solving a problem (impact) the small investor does not have.

## 7.1 The execution-cost physics (what institutions are actually fighting)

- **Implementation shortfall** — the gap between the paper portfolio at decision price and the
  real one — is the standard institutional cost metric since Perold 1988 (V, [JPM Spring
  1988](https://jpm.pm-research.com/content/14/3/4)). Everything below is machinery for
  minimizing it.
- **The square-root impact law** is the empirical bedrock: a metaorder of size Q moves price
  ∝ σ·√(Q/V), roughly independent of execution schedule — described by Bouchaud as one of the
  most robust regularities in market microstructure, holding across equities, FX, futures,
  options ([V academic](https://arxiv.org/pdf/2205.07385); recent confirmations on Nasdaq
  ITCH data and Tokyo exchange data, where a "double square-root" refinement suggests impact is
  largely *mechanical*, not informational). Practical meaning: cost scales with the square root
  of your size relative to daily volume — which is why "how big are we vs ADV" governs
  everything institutional and *nothing* retail.
- **Almgren–Chriss (2000)** — the impact-vs-timing-risk optimization — is the scaffolding of
  every broker algo suite (VWAP/TWAP/IS/POV are special cases of it), not something PMs invoke
  directly (SI, consistent practitioner literature).
- **Measured institutional costs (Ancerno data, V peer-reviewed):** one-way execution shortfall
  averaged ~13 bps in 2007, spiking to ~30 bps in October 2008 (Anand–Irvine–Puckett–
  Venkataraman). Costs trended down after 2003. Vendor TCA figures (Virtu: VWAP slippage
  ~2.3 bps large-cap vs ~5.7 bps small-cap, 2021) are WI — single-vendor, treat as magnitudes.
- **The live-data dispute, preserved:** Frazzini–Israel–Moskowitz, using ~$1tn of AQR's actual
  trades (V that the papers exist and their abstract-level findings): real trading costs are
  **less than one-tenth** of prior academic estimates and factor-strategy capacity is an order
  of magnitude larger; size/value/momentum survive costs at scale, short-term reversal does not
  (consistent with Phase 2 §11). **Patton–Weller disagree** — average realized institutional
  anomaly costs are far higher; AQR may be an unusually patient trader, not representative.
  **Disagreement preserved, not resolved.** Working rule for Phase 12: cost-model at
  Patton–Weller pessimism, celebrate if FIM optimism shows up. Note FIM's within-paper per-trade
  bps tables were not re-verified from the PDF this pass — U on precise per-trade figures;
  spot-verify in the Phase 16 pass if any Phase 12 system leans on them.
- **Algo vs high-touch mix:** ~80% of buy-side order flow touches algos/SORs per Coalition
  Greenwich surveys, but survey definitions (flow touched vs dollar volume executed) conflict
  across years — SI for the electronic trend, WI for any specific percentage. Off-exchange
  volume reached ~44.5% of US equity volume in Q1 2024, but pure dark-pool ATS share is only
  ~15–18% — the rest is wholesaler internalization of retail flow (SI, FINRA-derived via
  secondary aggregators).

## 7.2 Entry — documented institutional practice

### The stealth-accumulation record

| Case | Mechanics | Evidence |
|---|---|---|
| Berkshire–IBM 2011 | Bought from March 2011, ~5.5% (~$10.7bn) over ~8 months before disclosure, using **13F confidential treatment**; Buffett's stated rationale: mid-accumulation disclosure "would be unfair" to his shareholders | V mechanics ([13F-HR with omitted holdings](https://www.sec.gov/Archives/edgar/data/0001067983/000119312511223118/d13fhr.txt)); MS rationale ([CNBC transcript](https://www.cnbc.com/2011/11/14/cnbc-transcript-warren-buffett-explains-why-he-bought-107b-of-ibm-stock-part-5.html)) |
| Berkshire–Chubb 2023–24 | Same CT mechanism across multiple quarters before the May 2024 reveal. Counterweight: the SEC **denied** Berkshire CT requests in 2003/2004 ([order](https://www.sec.gov/rules-regulations/2004/08/berkshire-hathaway-inc-order-denying-requests-confidential-treatment)) — CT is discretionary, not an entitlement | V |
| Berkshire–Coca-Cola 1988–89 | Patient open-market accumulation, $593M in 1988 + $431M in 1989, no blocks; disclosed via the shareholder letter | MS/V |
| Pershing Square–Allergan 2014 | The canonical derivative-stealth entry, per the actual 13D (V, [filing](https://www.sec.gov/Archives/edgar/data/0000850693/000119312514150906/d711603dsc13d.htm)): crossed 5% April 11, 2014, then accumulated ~13.95M additional shares of exposure *inside the then-10-day window* via American calls + forward purchase contracts, reaching 9.7% by the April 21 filing. **Fallout:** Rule 14e-3 suits settled Dec 2017 for $290M (Pershing $193.75M / Valeant $96.25M), no admission (V) | V |

- **The trigger-day pattern is systematic, not anecdotal:** Bebchuk–Brav–Jackson–Jiang
  (~2,000 activist 13Ds, 1994–2007 — V academic): share turnover on the day of crossing 5% runs
  ~**325% of normal volume** — activists concentrate buying on and immediately after the trigger;
  ~10% of 13Ds were filed late. This is precisely what the October 2023 rule targeted: initial
  13D deadline cut 10 calendar days → **5 business days**, amendments 2 business days (V, [SEC
  release](https://www.sec.gov/newsroom/press-releases/2023-219)); SEC guidance says mere
  shareholder communication alone doesn't form a "group" — the wolf-pack question survives.
- **Sizing-at-entry doctrine (fundamental side):** Druckenmiller's stated Soros lesson —
  "sizing is 70–80% of the equation… it's how much you make when you're right and how much you
  lose when you're wrong"; concentrate when conviction is high (MS, interviews). This is an
  *entry* doctrine only in combination with his exit doctrine (§7.3) — bet big *because* you
  will exit fast if wrong. Copying the first half without the second is the documented Tiger
  2022 shape.
- **Platform entry practice:** pods enter small, event-keyed, inside centrally imposed limits;
  the drawdown ladder (Phase 5/6, SI, no primary) forces the entry to be reversible. The pod's
  entry plan *is* its risk plan.
- **Multi-day slicing is universal:** Chan–Lakonishok (JF 1995 — V) showed the institutional
  unit of trading is the multi-day "package," not the order; Ancerno-based studies reconstruct
  parent orders spanning multiple brokers and consecutive days. Typical parent-order duration:
  U — no public standard exists.

### What entry looks like when it fails

Archegos is the entry-failure control as well as the risk one: >10% of float in single names
accumulated *entirely via swaps* (V, court records), meaning entry was possible but exit was
mechanically impossible — the position was larger than the door. Phase 6's days-to-exit grammar
(≤20–25% of ADV) exists precisely to prevent entering what you cannot leave.

## 7.3 Exit — the documented disciplines

The exit taxonomy, each trigger with its best-documented exemplar:

| Exit trigger | Exemplar | Evidence |
|---|---|---|
| **Thesis broken → exit immediately at any price** | Ackman–Netflix, April 2022: bought ~$1.1bn Jan 2022; sold the *entire* stake within ~a day of the 200k-subscriber-loss print at ~$225, realizing ~$400–430M loss. Stated reason: "we have lost confidence in our ability to predict the company's future prospects" | V/MS ([PSH letter via press](https://deadline.com/2022/04/bill-ackman-pershing-square-netflix-1235007039/)) |
| **Wrong = out (macro/trading doctrine)** | Druckenmiller: "Never hang onto a security if the reason you bought it has changed"; Soros described as pre-defining what would prove him wrong and acting instantly | MS (interviews/memoirs) |
| **Fundamental deterioration / story over, never macro fear** | Lynch's category-specific rules (stalwarts out after ~50% gain in 1–2 yrs; fast growers out when growth ends): "if you know why you bought it, you'll automatically have a better idea of when to say goodbye" | MS (*One Up on Wall Street*) |
| **Opportunity-cost replacement** | Buffett/Munger: "Everything should be done in terms of opportunity cost" — sell/hold framed against the best alternative, not price targets | MS (meeting remarks) |
| **Valuation/tax/de-risk, staged** | Berkshire–Apple 2024: 115M shares Q1, ~390M Q2 — ~2/3 of the stake exited across quarters via ordinary staged selling, disclosed in 10-Q/13F; stated rationale tax (MS), read by analysts as valuation/de-risking beyond taxes (SI) — **both readings preserved** | V mechanics |
| **Salvage exit (thesis dead, position huge)** | Ackman–Valeant, March 2017: entire stake out in one **block sale via Jefferies** — 27.2M shares at ~$11.10–11.40 (~$300M) against ~$4.6bn invested; the block dealer took the balance on its book | SI (contemporaneous press; block mechanics not in filings) |
| **Forced exit** | Melvin, Jan 2021: GME short covered by the afternoon of Jan 26 after $2.75bn Citadel/Point72 infusion; cover mechanics U | V timing / U mechanics |

- **The speed spectrum is the finding:** thesis-break exits are *fast* (Netflix: ~a day;
  documented and survivable because position ≪ ADV-days), valuation exits are *slow and staged*
  (Apple: quarters), salvage exits are *blocks at whatever the dealer will pay* (Valeant: >90%
  loss crystallized in one print). The discipline isn't a speed — it's that **the trigger type
  was decided before the trigger fired** (Phase 4 step 24's pre-registered invalidation).
- **Hedging as exit-alternative (Phase 6's kept distinction):** PSH's Feb 2020 CDS and 2022
  rates options were *specific identified risks bought cheaply* (V, ARs) — used where exit was
  undesirable but a named risk was live. No documented survivor runs standing tail programs as
  a substitute for exit discipline (SI, industry literature).

### The failure-to-exit record (updates Phase 6's table with exit-side specifics)

- **Sequoia–Valeant (V/SI, now with the number Phase 1 flagged):** Valeant reached **~32% of
  fund assets** mid-2015; the fund refused to sell any shares through a ~93% collapse
  (Aug 2015–Jun 2016); fund -34%, trailing the S&P by ~31pp; the CEO/co-manager resigned. The
  governance post-mortem is the useful part: *one person could paralyze the sell decision*;
  fixed afterward with a 4-to-1 committee vote rule plus position caps. Exit discipline is a
  governance property, not a personality trait.
- **Tiger Global 2022 (SI):** exited only ~7 of 54 public holdings outright during a -56% year —
  mostly held through, while marking privates down ~33% (~$23bn). No documented pre-registered
  invalidation anywhere in the record.
- **Archegos, the unwind race (V/SI — the definitive "who sells first" case):** Morgan Stanley
  quietly sold ~$5bn of collateral to fewer than six funds on the night of Thursday March 25,
  2021 — *before* the fire sale was public; Goldman ran ~$10.5bn of discounted blocks the next
  morning to a wide list. GS and MS escaped nearly whole; slower Credit Suisse lost ~$5.5bn,
  Nomura ~$2bn. (MS/GS/Wells later paid $120M over Archegos-related disclosure.) Lesson,
  documented at bank scale: **in a correlated unwind, exit speed is the whole game, and the
  slowest seller absorbs the entire loss.** The retail translation is Phase 6's liquidity cap:
  never be the size where this race applies to you.

## 7.4 Timing patterns (V academic, all)

- **Intraday U-shape** in volume/volatility/spreads persists in the electronic era; the close
  auction has grown into the institutional rebalancing venue (open = information trading,
  close = rebalancing). Retail translation: the open is the most adversely selected time of day
  to trade; the close is the most liquid.
- **Window dressing vs tax-loss selling:** the peer-reviewed literature genuinely disagrees
  (Lakonishok et al. 1991 and He–Ng–Wang 2004 for window dressing; Sias–Starks 1997 and
  Poterba–Weisbenner 2001 for tax-loss selling; newer actual-trade evidence finds turn-of-year
  effects strongest in stocks institutions *don't* trade, undercutting both). **Disagreement
  preserved.** Nothing in Phase 12 may lean on quarter-end predictability.
- **Institutions do earn intra-quarter trading profits** (Puckett–Yan, JF 2011 — V), i.e., the
  13F quarterly snapshot understates institutional skill — a caveat Phase 8 inherits directly.

## 7.5 Findings for Phase 12/15

1. **The retail execution advantage is real and structural.** Every dollar institutions spend on
   TCA, algos, CT requests, and swap accumulation is spent fighting √(Q/V) impact. At retail
   size in liquid names, Q/V ≈ 0: marketable limit orders near the close capture what Citadel
   pays a floor of PhDs to approximate. The corollary: this advantage *vanishes* in illiquid
   small caps, where spread (not impact) is the cost — consistent with Phase 2/3's finding that
   the same small caps that carry the remaining anomalies carry the costs that eat them.
2. **Entry rule seed:** size so that exit-in-one-day is always possible (position ≤ a small
   multiple of your honest share of ADV); enter in tranches only if the entry plan (including
   add-on-decline conditions) was written before the first tranche — otherwise tranching is just
   averaging down with extra steps (Phase 6's test applies from the first share).
3. **Exit rule seed — the strongest single pattern in the whole study so far:** pre-register the
   invalidation, and let trigger *type* set exit speed: thesis-break → immediate, full,
   price-insensitive (the Netflix template); valuation/target → staged and unhurried (the Apple
   template); never let a thesis-break exit be executed on the valuation-exit timetable (the
   Sequoia/Tiger failure shape).
4. **Governance seed:** the Sequoia fix (supermajority to *hold* past a cap breach, not to sell)
   inverts the veto correctly — selling should be the default that requires no permission.
   Phase 15 imports this as: breach of a pre-committed boundary executes automatically; only
   *overriding* the exit needs a written case.
5. **Timing seeds:** avoid the open; prefer the close; assume nothing about quarter-end.
6. **Cost-model seed for Phase 13:** backtest at Patton–Weller-pessimistic costs (tens of bps
   one-way in small caps), not FIM-optimistic ones; any strategy that dies at 30 bps one-way was
   never alive.
