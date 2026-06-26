# DSE Buy/Sell Research Log

> Personal trading research for DSE — **end-of-day decision support**, separate from the public
> portal (which stays descriptive-only). Goal: a multi-horizon, **data-driven** engine that ranks
> candidates and helps catch moves early. Started 2026-06-26. Data as of EOD 2026-06-24/25.

## 0. Hard constraints (these shape everything)

- **Data is EOD / delayed** (dsebd.org). No intraday, no live tape. → swing / positional / investing,
  **not** day-trading. There is **no broker/execution link** for DSE here — the engine produces a
  reasoned shortlist + levels; orders are placed manually.
- **Single-regime history.** Bars span 2024-06 → 2026-06 (~476 trading days), which is the
  *post-floor-price* DSE (sharp decline then recovery). Every finding below is **regime-specific** and
  must be re-validated as history accumulates.

## 1. Data inventory (what the engine reads)

| Dataset | Rows | Span | Use |
|---|---|---|---|
| daily_bars (OHLCV) | 188k | 2024-06 → 2026-06 | price history, backtest substrate |
| ticker_analytics | 396 | latest EOD | RSI/SMA/ATR/CMF/52w + P/E,P/B,yield,pe_vs_sector,EPS-growth,ownership |
| market_summary | 475 | 2yr | DSEX/DS30, turnover, breadth |
| company_profiles | 396 | latest | sector, float, debt, reserves, dividend |
| shareholding_snapshots | 1,188 | ~3/stock | ownership % over time (sparse!) |
| company_financials | 1,946 | 2012→2025 | multi-year EPS/NAV/profit |
| company_dividends | 4,542 | 1983→2025 | cash + bonus history |
| sector_pe | 18 | latest | relative valuation |

## 2. Factor efficacy — does anything predict forward returns? (`scripts/factor_study.py`)

Method: reconstruct each factor **point-in-time** at ~17 monthly rebalances, measure the
Information Coefficient (Spearman rank corr) vs forward 20- and 60-day returns. IC>0 = ranked winners;
IR = mean/std = reliability.

| Factor | IC@20d (hit%) | IC@60d (IR, hit%) | Verdict |
|---|---|---|---|
| momentum | −0.052 (35%) | −0.077 (24%) | **negative — trend-following hurt** |
| value | +0.009 (41%) | −0.012 (47%) | flat |
| quality | +0.036 (53%) | +0.056 (53%) | mildly positive |
| **contrarian** | **+0.063 (65%)** | **+0.071 (65%)** | **best family** |
| ↳ oversold RSI | +0.066 (71%) | **+0.094 (IR 0.52, 82%)** | **strongest single signal** |

**Headline:** On this window, **mean-reversion beat momentum decisively.** Buying oversold (low RSI)
positively predicted 60-day returns on **82% of rebalances**. Trend-chasing was counterproductive.

**Caveats:** all ICs are weak in absolute terms (|IC|<0.1); 17-date sample; single regime;
value/quality use a reporting lag; survivorship (today's listed names only).

## 3. Precursor study — what a base looks like *before* it launches (`scripts/precursor_study.py`)

Method: detect each name's launch trough, measure the base leading into it, contrast big runners
(≥60% in 60d, n=70) vs quiet names (<20%, n=60).

| Pre-launch feature | BIG | QUIET | Read |
|---|---|---|---|
| % below 1-yr high | **−59%** | −29% | launches come from **deep washouts** |
| position in 52w range | **1.9%** | 10% | sitting **on the 52-week low** |
| daily-return stdev (coil) | 2.95% | 1.57% | **volatile capitulation, not a quiet coil** |
| volume surge into low | 0.61 | 0.54 | both dry up — barely distinctive |
| up-day volume share | 0.39 | 0.41 | **no accumulation tell at the trough** |

**Signature:** deep, volatile washout at the 52-week low. Two counter-textbook findings: it is **not**
a low-volume coil (it's a high-volatility panic bottom), and there is **no visible volume
accumulation** before the turn — the move isn't telegraphed by volume.

**Caveat (important):** drawdown-depth and 52w-position are *partly mechanical* (the trough is defined
as the lowest close), so this identifies the **zone**, not the **trigger/timing**. The trigger is the
open question.

## 4. Live result — launch-zone watchlist (as of 2026-06-24)

Signature applied today (deep washout + near 52w low, liquid): **9 names**.

| Code | % below high | % above low | RSI | inst Δ | Sector |
|---|---|---|---|---|---|
| BEXIMCO | −71% | 0% | 0 | −0.01 | Misc |
| KBPPWBIL | −74% | 5% | 31 | −1.21 | Misc |
| RELIANCE1 | −45% | 6% | 43 | −1.91 | Mutual Fund |
| AL-HAJTEX | −46% | 9% | 48 | −3.53 | Textile |
| MIDLANDBNK | −46% | 10% | 53 | −0.56 | Bank |
| STANDBANKL | −41% | 12% | 56 | −0.48 | Bank |
| PREMIERBAN | −46% | 13% | 56 | −0.05 | Bank |
| GEMINISEA | −45% | 14% | 47 | −0.13 | Food |

Institutional Δ is uniformly negative — no accumulation confirmation, matching §3. These are
**watch-for-a-turn candidates, not buys** (no trigger yet).

## 5. Why no deep ML (yet)

PatchTST / deep time-series transformers need thousands of clean examples; we have ~100 movers over a
2-year single-regime window. A deep model would overfit and look great in-sample, then fail live
(violates "right tool, not trendy tool"). The validated path: precursor/event study → **a small,
interpretable classifier** (gradient-boosted trees / logistic) on the engineered features **once a
trigger signal is confirmed** — not before.

## 6. Tools

| Script | Purpose |
|---|---|
| `scripts/shortlist.py` | ranked daily buy/sell shortlist; calibrated weights (contrarian+quality led) |
| `scripts/factor_study.py` | factor IC calibration (§2) |
| `scripts/precursor_study.py` | pre-launch base signature (§3) |

## 7. Open threads / next steps

1. **Trigger study** — within deep-base names, what marks the *turn*? (first higher-low, RSI crossing
   up from oversold, first up-day volume expansion). The timing the zone-signature lacks.
2. **Live launch-zone detector + forward validation** — scan daily; validate *without* trough-
   conditioning (removes the §3 tautology) to prove it predicts.
3. **Strategy backtest** — "buy top-N shortlist monthly, hold 20/60d" → return curve vs DSEX. Turns
   IC into P&L. The proof before trading.
4. **Flow calibration (later)** — ownership history is too sparse now (~3 snapshots/stock); the weekly
   scrape is accumulating it for a future test.
5. **Outlier guard** — winsorize EPS-growth (e.g. KBPPWBIL "+2600%" base effect) before scoring.
