# Spec: Scanner — "Radar" + "Setups" (স্ক্যানার)

**Status:** Draft, research-reviewed → **build-ready (review edits applied)** · **Owner:** Ilias · **Date:** 2026-07-01
**Surface:** Replaces the Watchlist tab. Nav: ⭐ Watchlist → 🛰️ Scanner.

---

## 0. Review log (2026-07-01, Claude — reconciled vs codebase + `docs/research/dse-trading-research.md`)

1. **Hero board = "Quality Reversal", not raw "Deep Washout Reclaim."** The research flagship is
   **Scheme-3**: washout + 5-day-high break **filtered to profitable, reasonably-priced names**
   (+73.6% vs +33.7%, 58% vs 41% win, −12% vs −21% drawdown — "the two proven edges *multiply*").
   The first draft split the winning combo into two boards and headlined the weaker half. Fixed in
   §3/§6: hero = Quality Reversal; raw deep-washout is demoted to an advanced/experimental board.
2. **Regime caveat is mandatory on the reversal boards.** The research: the whole washout edge rests
   on one *recovering*-market window; "deepest = falling knife in a sustained bear." Reversal boards
   carry a regime note, gated by the Dhaka Mood Index / DSEX-vs-200-DMA. See §2, §7.
3. **Circuit "at" tolerance fixed for tick-rounding.** `factors.py` documents that locked stocks
   settle ~9.7–9.95 under a 10% band. So "at circuit" = `|change| ≥ band − 0.3` (not `− 0.05`, which
   would miss locked names); "near" = `band − 0.6`. See §5.1.
4. **`circuit_band()` is shared and retrofits the existing Circuit desk.** `factors.py` currently
   posts at a flat 9.7% — it must call the same tiered helper, or the Scanner and the Circuit desk
   contradict each other. Helper lives in `bulls.analytics`.
5. **Active Today reuses the validated EOD `trending_scores`** (backtested, already live on Markets),
   *not* a new unbacktested intraday computation. An intraday "tape" version, if added later, is
   labelled experimental and reuses `volume.py`'s `session_fraction()`.
6. **Markets ↔ Scanner boundary defined** (new §1a) so we don't ship two tabs with the same lists.
7. **5-day-high break isn't in `ticker_analytics`** — persist a `broke_5d_high` flag at EOD (cheap)
   rather than claim "no recompute." See §6 note.
8. **Dividend board drops "above sector"** (we don't compute sector-average yield) → "high yield +
   positive EPS + coverage." Omit over mislead.
9. **Centralize the liquidity gate** — `_MIN_ADTV_MN` is copy-pasted in 4 files already; add one
   shared helper, don't make a 5th.
10. **Settlement (T+2/T+3) moves to the symbol page**, not every scanner row (execution detail, not a
    scan condition).

---

## 1. Problem & intent

The Watchlist tab is passive — it only lists stocks you already chose. We have a rich analytics +
signal engine but no place to actively *hunt* with it. A scanner turns the app from "read the data"
into "hunt with the data" — the tool a trader keeps open through the session. It's the strongest
engagement lever after the feed.

The product should feel simple even if the engine underneath is institutional-grade. Phase 1 should
answer three retail/value-trader questions fast:

1. **What is active today?** Unusual turnover/volume, not hype.
2. **What looks worth studying?** Value, quality, dividend and reclaim candidates.
3. **What is happening in my own list?** Same scans, scoped to watched stocks.

User-facing tabs for Phase 1:

- **আজ / Today** — the fast session read: Active Today, Deep Washout Reclaim, and key movers.
- **ভ্যালু / Value** — slower investor read: Value + Quality, Dividend Quality, and cheap-vs-sector.
- **ওয়াচলিস্ট / Watchlist** — user's watched stocks, plus the same scanner labels on only those names.

Internally the API can still call these Radar and Setups, but the visible product should not feel like
a dense trading terminal.

The existing watchlist is not lost; it becomes the Watchlist tab inside Scanner (see §8).

Custom **Build-a-Scan** (user-defined conditions + save + alert) is explicitly **out of scope** for
this phase — it's the next phase (§11).

## 2. Principles & guardrails (non-negotiable)

- **Descriptive, never advisory.** A scan surfaces stocks *meeting a stated condition* — a fact. It
  never says buy/sell/target. Setup names describe the pattern, not a call ("Oversold Bounce" carries
  the "could also be a falling knife" caution, like the screens already do).
- **Never fake freshness.** DSE is 15-min delayed intraday; there is no true real-time. "Live" = as
  fresh as the feed allows, refreshing through the session, with a visible `as_of` / delayed stamp
  (same discipline as TickerStrip / MarketPulse).
- **Liquidity-gated.** Reuse the screener's gating (min ADTV, min market cap, Z-category handling) so
  the Radar surfaces tradeable names, not the same illiquid circuit small-caps.
- **DSE rule-aware.** Circuit detection must use the BSEC/DSE tiered price-band table, not a flat
  +/-10%. Settlement copy defaults to DSE T+2 for ordinary listed equities, with Z-category shown as
  higher-risk/T+3 where applicable.
- **Evidence before hype.** The scanner should lead with signals that have worked on our DSE data:
  self-normalized volume/turnover anomaly and deep-washout reclaim. Generic momentum/breakout is
  allowed only as descriptive context or an experimental scan, not the hero setup.
- **Important things first.** The default screen shows only 3-5 high-signal boards. Circuit, Z-category,
  smart-money disclosure, overbought/oversold, support/resistance, and experimental momentum stay
  behind "More filters" or "All".
- **One-row clarity.** A row should answer: why this stock is here, whether it is liquid enough, and
  what to check next. Do not expose every metric in the row; put details in the bottom sheet.
- **Omit over mislead.** A condition we can't compute for a name simply excludes it; empty groups are
  hidden, not faked.
- **Bangla-first, mobile-first.** Group/setup names + the "what it is" lines are bilingual.

## 3. Phase 1 simplicity cut

Default visible boards:

| Tab | Board | Purpose | Why visible first |
|---|---|---|---|
| Today | 🔥 Active Today | Stocks with unusual volume/turnover vs their own normal | Best validated activity signal; useful to small traders without implying buy/sell. |
| Today | 🌊 Quality Reversal | Beaten-down **but profitable & reasonably-priced** names breaking their 5-day high | Research flagship (Scheme-3): washout × quality *multiplied* the edge (+73.6%, 58% win, −12% dd). Carries a regime caveat (§2). Raw deep-washout without the quality filter is an advanced/experimental board only. |
| Today | 💸 Top Turnover | Where money is actually trading today | Familiar to DSE retail users; liquidity-gated so it is not pure noise. |
| Value | ⭐ Value + Quality | Cheap vs sector plus profitability | Core value-trader board. |
| Value | 💵 Dividend Quality | Cash yield with EPS/record-date/checklist context | Useful for income/value users; avoids yield traps with checks. |
| Watchlist | ⭐ My Watchlist Signals | Any of the above, filtered to watched codes | Converts passive watchlist into useful monitoring. |

Hidden under **More filters / All**:

- Near circuit
- Big movers
- Oversold / overbought
- Near support / resistance
- Smart-money disclosure
- Quiet accumulation
- Momentum / near high
- High-risk / Z

Default row content should stay compact:

- ticker + setup label
- price and 1D change
- one human reason line
- liquidity tag (`গভীর`, `লেনদেনযোগ্য`, `অর্ডার সাইজে সতর্কতা`)
- tap opens detail sheet; full stock-page CTA stays inside the sheet

## 4. Research-backed changes from the first draft

These are hard changes before implementation:

- **Circuit group:** replace `change_pct >= +/-9.7%` with a function based on the current BSEC circuit
  order. From 09 Jun 2026, BSEC restored the 17 Jun 2021 tiered circuit limits for listed securities:
  up to Tk 200 = 10%, above 200-500 = 8.75%, above 500-1000 = 7.5%, above 1000-2000 = 6.25%, above
  2000-5000 = 5%, above 5000 = 3.75%.
- **Z-category:** exclude Z from clean/default scanner groups. If shown, place it in a separate
  high-risk group with explicit Z/T+3 risk copy. BSEC Z rules include dividend, AGM, operational,
  retained-earnings, and dividend-payment failure triggers.
- **Momentum:** do not headline "Momentum Breakout." Our own DSE research shows momentum/trend
  following was weak or negative in the current sample; mean-reversion/deep-washout behavior was
  stronger.
- **Active tape:** use the validated `Active today` logic as the center of Radar: self-normalized
  volume + turnover surge, direction-agnostic, liquidity-gated, no pump language.

## 5. DSE market rules encoded in the scanner

### 5.1 Circuit bands

Implement a shared helper so the API, labels and tests use the same rule.

| Reference price | Circuit band |
|---|---:|
| Up to Tk 200 | 10.00% |
| Above Tk 200 to Tk 500 | 8.75% |
| Above Tk 500 to Tk 1,000 | 7.50% |
| Above Tk 1,000 to Tk 2,000 | 6.25% |
| Above Tk 2,000 to Tk 5,000 | 5.00% |
| Above Tk 5,000 | 3.75% |

Detection:

- `band = circuit_band(reference_price)` where reference price is previous close / DSE reference
  price used by the quote feed.
- **At circuit:** `abs(change_pct) >= band - 0.30` (NOT `- 0.05`) — locked stocks settle a touch under
  the band from tick rounding (`factors.py` documents ~9.7–9.95 under a 10% band), or use an
  exchange-provided circuit flag if available.
- **Near circuit:** `abs(change_pct) >= band - 0.60` so retail sees names approaching the limit before
  they are fully locked.
- Direction labels must be factual: "near upper circuit", "near lower circuit", "at upper circuit",
  "at lower circuit".

### 5.2 Category and settlement

- Default investable scanner: visible, active, non-hidden, non-Z symbols only.
- Default liquidity gate: reuse the Market screener gate:
  - 20D ADTV >= Tk 50 lakh (`_MIN_ADTV_MN = 5.0`)
  - market cap >= Tk 50 crore (`_MIN_MCAP_MN = 500.0`)
  - free-float cap >= Tk 10 crore when available (`_MIN_FREE_FLOAT_CAP_MN = 100.0`)
- Settlement label: ordinary listed equity = T+2. Z-category = separate high-risk read; BSEC
  directives state Z-category clearing day as T+3, excluding spot/DVP exceptions.
- Never mix Z names into clean "setup" groups. Show them only when the user explicitly opens
  `High-risk / Z` or `All`.

## 6. Scanner boards

Each board is a fast SQL read over already-persisted data (no recompute), top-N, liquidity-gated,
ordered by the board's own metric. Intraday boards read `quote_snapshots`; structure/factor boards
read `ticker_analytics` (refreshed EOD). All freshness-stamped.

| Board | Default visibility | Condition (source) | Order by | Notes |
|---|---|---|---|---|
| 🔥 Active Today | Today tab | Intraday turnover/volume pace >= 2x normal, using `quote_snapshots.volume * ltp` vs `ticker_analytics.avg_volume_20 * last_close`, day-fraction scaled during session when available | anomaly score | Core board. Direction-agnostic; label as activity, not strength. |
| 🌊 Deep Washout Reclaim | Today tab | `pct_from_52w_high <= -40%` · `pct_from_52w_low <= 15%` · latest close breaks prior 5-day high | trigger quality, then liquidity | Stronger fit to our DSE research than generic breakout. |
| 💸 Top Turnover | Today tab | highest `quote.volume * quote.ltp` today | turnover | Familiar to DSE retail; keep liquidity-gated. |
| ⭐ Value + Quality | Value tab | `pe_vs_sector < 0.8` · `roe >= 15%` · positive EPS where available | quality-adjusted cheapness | Value-trader core. Copy must warn about value traps. |
| 💵 Dividend Quality | Value tab | cash dividend yield above market/sector, positive EPS where available, Cat A/B/N/G, non-Z | yield then coverage | Retail-friendly; explain record date and price adjustment in the sheet. |
| ⚡ Near Circuit | More filters | `abs(quote.change_pct) >= circuit_band(ref_price) - 0.30` | distance to band | Uses tiered DSE circuit helper. Split upper/lower labels. |
| 📈 Big Movers | More filters | top gainers / losers by `quote.change_pct` | \|change\| | Useful, but not a recommendation and not a hero board. |
| 🎯 Near Support / Resistance | More filters | EOD `last_close` within 3% of `nearest_support`/`nearest_resistance` | proximity | Structure read; stamp as EOD, not intraday. |
| 🌊 Oversold / Overbought | More filters | `rsi_14` <= 30 / >= 70 | RSI extremity | EOD technical state. |
| 🏦 Disclosure Moves | More filters | `institute_delta + foreign_delta` >= 1pp or <= -1pp | pp | Not live. Stamp disclosure date/month clearly. |
| 🧲 Quiet Accumulation | More filters | `cmf_20 >= 0.10` · `obv_slope > 0` · price within +/-10% of `sma_50` | CMF | Experimental watch pattern, not proven at troughs. |
| 🧪 Momentum / Near High | More filters | `pct_from_52w_high >= -3%` · `relative_volume >= 1.5` · `above_sma_200` | descriptive strength | Experimental/descriptive only. |
| ⚠ High-risk / Z | All/Risk only | Z-category, thin ADTV, pump-like run, circuit-locked lower | risk severity | Hidden from default clean view. |

Implementation note: most structure boards can reuse `build_screen`; live `Active Today`, `Near
Circuit`, `Top Turnover`, and `Big Movers` should read `quote_snapshots` joined to `ticker_analytics`
and `symbols` for liquidity/category context. If build time is tight, implement only the six default
boards first and leave More filters for the next slice.

## 7. Detail sheet copy

Every board response includes enough copy for a simple bottom sheet. No advice.

Required fields:

- `plain_label`: short Bangla-first board label.
- `what_it_is`: one sentence explaining why the stock appears.
- `how_to_read`: one sentence explaining how retail/value traders can use the information.
- `risk_note`: what the pattern does **not** prove.
- `check_next`: 3 concrete checks, e.g. news, support/resistance, ADTV/order guide, EPS, disclosure
  date.

Example for Deep Washout Reclaim:

- **What it is:** "দাম ৫২-সপ্তাহের লোর কাছে অনেক নিচে ছিল, এখন সাম্প্রতিক ৫ দিনের হাই ভেঙেছে।"
- **How to read:** "এটি সম্ভাব্য turn attempt দেখায়; নিশ্চিত হওয়ার জন্য ভলিউম, খবর ও সাপোর্ট
  ধরে আছে কি না দেখুন।"
- **Risk note:** "গভীর পতনের শেয়ার আরও পড়তে পারে; এটি buy signal নয়।"

Example for Value + Quality:

- **What it is:** "এই শেয়ারের P/E খাতের তুলনায় কম, আর ROE ভালো।"
- **How to read:** "এটি value shortlist-এর জন্য; EPS, ঋণ, খবর ও দাম ইতিমধ্যে কত উঠেছে দেখুন।"
- **Risk note:** "সস্তা মানেই ভালো নয়; দুর্বল ব্যবসা হলে এটি value trap হতে পারে।"

## 8. Watchlist folds in (the Watch page isn't lost)

The Scanner has a **scope toggle**: *Whole market* vs *⭐ My watchlist*. In watchlist scope every
default board is filtered to the user's watched codes — "scan only what I care about." A **My
Watchlist** segment lists the watched stocks with quotes and the ⭐ toggle to add/remove, so watchlist
management lives here. The `☆ Watch` control on symbol pages is unchanged; the Home feed still uses
the watchlist. Net: the watchlist gains a scanner; it loses nothing.

## 9. API

New router `services/api/src/api/routers/scanner.py` (mounted at root, tenant-scoped):

| Method | Path | Notes |
|---|---|---|
| GET | `/scanner/radar` | grouped live/EOD hits; `?watched=true` scopes to the caller's watchlist; `?risk=true` includes high-risk groups |
| GET | `/scanner/setups` | preset scans + their matches + localized "what it is" / "how to read" |
| GET | `/scanner/watchlist` | watched stocks with quote, liquidity, risk flags and star toggle metadata |

Response shape (radar):

```json
{
  "as_of": "2026-07-01",
  "quote_as_of": "2026-07-01T13:45:00+06:00",
  "groups": [
    {
      "key": "active_tape",
      "label": "Active tape",
      "freshness": "15m delayed",
      "source": "quote_snapshots + ticker_analytics",
      "hits": [
        {
          "code": "GP",
          "name": "Grameenphone",
          "ltp": 286.2,
          "change_pct": 1.4,
          "value": 2.7,
          "value_label": "x normal turnover pace",
          "category": "A",
          "settlement_cycle": "T+2",
          "liquidity": "Tradeable liquidity",
          "adtv_mn": 35.4,
          "safe_order_mn": 1.77,
          "turnover_mn": 42.1,
          "risk_flags": [],
          "why": "Turnover is running 2.7x normal pace; price +1.4%; Cat A.",
          "check_next": ["News", "Volume holds", "Support/resistance", "Order size"],
          "spark": []
        }
      ]
    }
  ]
}
```

Redis-cache briefly, e.g. 60s, to absorb polling. Cache keys must include tenant, locale, watched/risk
scope, and user id for watched scope.

## 10. Frontend

- **Route/nav:** replace `watchlist` with `scanner` (🛰️). New `Scanner.tsx` page.
- **Segmented control:** Today · Value · ⭐ Watchlist. More filters opens advanced boards. This is the
  simplest retail-facing shape; API names may remain `radar`/`setups`.
- **Rows:** reuse the screener row (ticker + setup badge + price + metric chip + sparkline), tapping
  opens a bottom sheet first, then CTA to full symbol page.
- **Bottom sheet:** same pattern as Market popup: quick read, why it appears, what to verify next,
  execution check, CTA to full stock page.
- **Refresh:** session-aware polling (like TickerStrip): every ~60s while the market is open, paused after close; freshness stamp always shown.
- **Empty/cold-start:** groups with no hits are hidden; if all empty (e.g. pre-open) show a "market's quiet — check back in the session" state + a link to Setups (which work on EOD data any time).
- **Language:** Bangla-first labels:
  - Active Today = "আজ অস্বাভাবিক লেনদেন"
  - Value + Quality = "সস্তা + ভালো মান"
  - Dividend Quality = "লভ্যাংশ + কভারেজ"
  - Near circuit = "সার্কিটের কাছে"
  - Deep Washout Reclaim = "গভীর পতনের পর ঘুরে দাঁড়ানোর চেষ্টা"
  - High-risk / Z = "উচ্চ ঝুঁকি / Z ক্যাটাগরি"

## 11. Phasing & acceptance

- **Phase 1 (simple scanner): Today + Value + Watchlist.** Read-only over persisted data; no new
  tables. Acceptance: the six default boards return sensible liquidity-gated sets; freshness stamped;
  watchlist scope filters correctly; empty boards hidden; descriptive copy, no advice; Bangla-first;
  real DSE circuit helper implemented for later boards; Z-category excluded from clean groups.
- **Phase 1.5: More filters.** Add Near Circuit, Big Movers, Support/Resistance, Oversold/Overbought,
  Disclosure Moves, Quiet Accumulation, Momentum/Near High, and High-risk/Z.
- **Phase 2: Build-a-Scan.** User-defined conditions (chips), saved scans (new `saved_scans` table),
  and **alerts** when a new stock enters a saved scan (rides the existing signal/notification path).
  This is the power/robustness tier and the retention multiplier.
- **Phase 3 (optional): a visual scanner** — sector treemap / momentum-vs-value bubble map.

## 12. Test cases

Minimum unit/integration tests before launch:

- Circuit band helper:
  - `200 -> 10%`, `200.01 -> 8.75%`, `500.01 -> 7.5%`, `1000.01 -> 6.25%`,
    `2000.01 -> 5%`, `5000.01 -> 3.75%`.
- Near-circuit detection uses the band for each price tier, not a fixed 9.7%.
- Default Radar excludes `Symbol.category == "Z"` and includes Z only with risk scope.
- Watched scope returns only the caller's watched codes.
- Active tape uses current quote turnover/volume against the symbol's own normal, not cross-sectional
  top gainers.
- Disclosure moves include disclosure date/month and do not claim "today's buying".
- Empty groups are hidden; if all groups empty, the page shows the calm/empty state.

## 13. References

- BSEC Order No. `BSEC/Surveillance/2020-975/219`, 17 Jun 2021: tiered upper/lower circuit bands.
  https://sec.gov.bd/slaws/Order_17.06.2021.pdf
- BSEC Order No. `BSEC/Surveillance/2020-975/558`, 08 Jun 2026: floor-price withdrawal for BEXIMCO
  and ISLAMIBANK; 2021 circuit bands effective for listed securities from 09 Jun 2026.
  https://sec.gov.bd/slaws/Order_08.06.2026.pdf
- BSEC Order No. `SEC/CMRRCD/2009-193/74(R)`, 15 Feb 2024: Z-category triggers and T+3 clearing day.
  https://sec.gov.bd/slaws/Order_15.02.2024.pdf
- BSEC Directive No. `BSEC/CMRRCD/2009-193/77`, 20 May 2024: Z-category shifting/placement and T+3
  clearing day, effective 02 Jul 2024.
  https://sec.gov.bd/slaws/Directive_regarding_Z_category_company_20.05.2024.pdf
- Internal: `docs/specs/trending-engine.md` — Active Today validation, volume/turnover anomaly.
- Internal: `docs/research/dse-trading-research.md` — DSE factor and deep-washout research.

## 14. Open questions

1. Nav slot: replace Watchlist outright (recommended) vs add Scanner and move Watchlist under Profile?
2. Refresh interval (60s?) vs battery/data on mobile — tune with real usage.
3. Should `High-risk / Z` be visible by default under a risk toggle, or only under `All`?
4. Should the deep-washout reclaim setup use 5-day-high break from EOD bars only, or allow intraday
   quote break once intraday high is reliably available?
5. Should Active Today use day-fraction scaling during the session, or avoid scaling until we have
   enough intraday observations to avoid false positives early in the day?
