# Spec: Scanner — "Radar" + "Setups" (স্ক্যানার)

**Status:** Draft (for review) · **Owner:** Ilias · **Date:** 2026-07-01
**Surface:** Replaces the Watchlist tab. Nav: ⭐ Watchlist → 🛰️ Scanner.

---

## 1. Problem & intent

The Watchlist tab is passive — it only lists stocks you already chose. We have a rich analytics +
signal engine but no place to actively *hunt* with it. A scanner turns the app from "read the data"
into "hunt with the data" — the tool a trader keeps open through the session. It's the strongest
engagement lever after the feed.

Two surfaces, one page (segmented control):

- **🛰️ Radar** — a live "what's hitting *now*" view: every DSE stock currently meeting a notable
  condition, grouped by signal, refreshing through the session.
- **🎯 Setups** — one-tap preset scans that combine conditions into recognizable, *explained*
  patterns (Momentum Breakout, Oversold Bounce, Quiet Accumulation, Smart Money, Value + Quality).

Plus a **⭐ My Watchlist** scope so the Watch page isn't lost — it's upgraded (see §5).

Custom **Build-a-Scan** (user-defined conditions + save + alert) is explicitly **out of scope** for
this phase — it's the next phase (§8).

## 2. Principles & guardrails (non-negotiable)

- **Descriptive, never advisory.** A scan surfaces stocks *meeting a stated condition* — a fact. It
  never says buy/sell/target. Setup names describe the pattern, not a call ("Oversold Bounce" carries
  the "could also be a falling knife" caution, like the screens already do).
- **Never fake freshness.** DSE is 15-min delayed intraday; there is no true real-time. "Live" = as
  fresh as the feed allows, refreshing through the session, with a visible `as_of` / delayed stamp
  (same discipline as TickerStrip / MarketPulse).
- **Liquidity-gated.** Reuse the screener's gating (min ADTV, min market cap, Z-category handling) so
  the Radar surfaces tradeable names, not the same illiquid circuit small-caps.
- **Omit over mislead.** A condition we can't compute for a name simply excludes it; empty groups are
  hidden, not faked.
- **Bangla-first, mobile-first.** Group/setup names + the "what it is" lines are bilingual.

## 3. Radar — the live groups

Each group is a fast SQL read over already-persisted data (no recompute), top-N, liquidity-gated,
ordered by the group's own metric. Intraday groups read `quote_snapshots`; structure/factor groups
read `ticker_analytics` (refreshed EOD). All freshness-stamped.

| Group | Condition (source) | Order by |
|---|---|---|
| ⚡ Circuit | `quote.change_pct` ≥ +9.7% / ≤ −9.7% | \|change\| |
| 🔊 Unusual volume | `ticker_analytics.relative_volume` ≥ 2 (intraday day-fraction scaled where available) | rel-vol |
| 🚀 Breaking out | `pct_from_52w_high` ≥ −2% AND `change_pct` ≥ +1% | proximity |
| 📈 Big movers | top gainers / losers by `change_pct` | \|change\| |
| 🌊 Oversold / Overbought | `rsi_14` ≤ 30 / ≥ 70 | RSI extremity |
| 🏦 Smart-money buying | `institute_delta + foreign_delta` ≥ 1pp (last disclosure) | pp |
| 🎯 Near support / resistance | `close` within X% of `nearest_support`/`nearest_resistance` | proximity |

Most of these already exist as screener screens (`unusual_volume`, `top_gainers`, `oversold`,
`near_support`, `foreign/institutional_buying`, …) — the Radar reuses `build_screen` where possible;
only the intraday circuit/movers read the live `quote_snapshots`.

## 4. Setups — preset combined scans

Each setup = 2–3 conditions AND-ed, returning matches + a one-line *"what this pattern is"* and a
*"how traders read it"* (descriptive, with the honest caveat). No advice.

| Setup | Conditions (all from `ticker_analytics`) |
|---|---|
| 🚀 Momentum Breakout | `pct_from_52w_high` ≥ −3% · `relative_volume` ≥ 1.5 · `above_sma_200` |
| 🌊 Oversold Bounce | `rsi_14` ≤ 32 · within X% of `nearest_support` (caution: could be a falling knife) |
| 🧲 Quiet Accumulation | `cmf_20` ≥ 0.10 · `obv_slope` > 0 · price within ±10% of `sma_50` |
| 🏦 Smart Money Moving | `institute_delta + foreign_delta` ≥ 2pp |
| ⭐ Value + Quality | `pe_vs_sector` < 0.8 · `roe` ≥ 15% |

These mirror the factor-signal detectors (`signals/factors.py`) but read the persisted row directly
(no posting). Thresholds start from the factor-signal constants and are tunable.

## 5. Watchlist folds in (the Watch page isn't lost)

The Scanner has a **scope toggle**: *Whole market* vs *⭐ My watchlist*. In watchlist scope every
Radar group / Setup is filtered to the user's watched codes — "scan only what I care about." A **My
Watchlist** segment lists the watched stocks with quotes and the ⭐ toggle to add/remove, so watchlist
management lives here. The `☆ Watch` control on symbol pages is unchanged; the Home feed still uses
the watchlist. Net: the watchlist gains a scanner; it loses nothing.

## 6. API

New router `services/api/src/api/routers/scanner.py` (mounted at root, tenant-scoped):

| Method | Path | Notes |
|---|---|---|
| GET | `/scanner/radar` | grouped live hits; `?watched=true` scopes to the caller's watchlist |
| GET | `/scanner/setups` | preset scans + their matches + localized "what it is" / "how to read" |

Response shape (radar): `{ as_of, quote_as_of, groups: [{ key, label, hits: [{code, name, ltp, change_pct, value, value_label, liquidity, spark?}] }] }` — reuses the screener row shape so the frontend row component is shared. Redis-cached briefly (e.g. 60s) to absorb polling.

## 7. Frontend

- **Route/nav:** replace `watchlist` with `scanner` (🛰️). New `Scanner.tsx` page.
- **Segmented control:** Radar · Setups · ⭐ Watchlist. Scope toggle (market / watched) on Radar+Setups.
- **Rows:** reuse the screener row (ticker + setup badge + price + metric chip + sparkline), tapping → symbol page.
- **Refresh:** session-aware polling (like TickerStrip): every ~60s while the market is open, paused after close; freshness stamp always shown.
- **Empty/cold-start:** groups with no hits are hidden; if all empty (e.g. pre-open) show a "market's quiet — check back in the session" state + a link to Setups (which work on EOD data any time).

## 8. Phasing & acceptance

- **Phase 1 (this spec): Radar + Setups + watchlist scope.** Read-only over persisted data; no new
  tables. Acceptance: groups/setups return sensible liquidity-gated sets; freshness stamped; watchlist
  scope filters correctly; empty groups hidden; descriptive copy, no advice; Bangla-first.
- **Phase 2: Build-a-Scan.** User-defined conditions (chips), saved scans (new `saved_scans` table),
  and **alerts** when a new stock enters a saved scan (rides the existing signal/notification path).
  This is the power/robustness tier and the retention multiplier.
- **Phase 3 (optional): a visual scanner** — sector treemap / momentum-vs-value bubble map.

## 9. Open questions

1. Nav slot: replace Watchlist outright (recommended) vs add Scanner and move Watchlist under Profile?
2. Radar refresh interval (60s?) vs battery/data on mobile — tune with real usage.
3. Do Setups need the "how traders read it" line inline, or behind an info-tap (to keep rows compact)?
4. Thresholds (§3/§4) are starting guesses from the factor constants — revisit with real DSE data.
