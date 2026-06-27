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

## 4b. Signal backtest — does the turn-trigger pay, out of sample? (`scripts/signal_backtest.py`)

Walks the full history day by day (no lookahead). At each date, for each liquid name: in the launch
zone (>40% below 1yr high AND within 15% of 52w low) AND a turn-trigger fires → measure forward
**3-month** (63d) return, run-to-peak, worst-dip. Baselines: any liquid name +3.5% (48% win); DSEX
−0.4% (flat-down market).

| Trigger | n | win% | mean | median | peak | dip | vs base |
|---|---|---|---|---|---|---|---|
| zone only | 1631 | 58% | +11.5% | +5.1% | +23% | −11% | +7.9 |
| **break 5d high** | 370 | **59%** | +16.3% | +5.3% | +26% | **−9.9%** | +12.8 |
| RSI x-up 35 | 627 | 57% | +16.3% | +4.7% | +23% | −11% | +12.7 |
| two up days | 768 | 58% | +15.0% | +5.8% | +25% | −10% | +11.4 |
| cross SMA10 | 790 | 55% | +10.7% | +3.2% | +22% | −12% | +7.1 |

**Stability:** every trigger positive in BOTH the early and late half of signals (out-of-sample sanity
holds). **Reads:** the zone carries most of the edge; the trigger adds win-rate + tighter downside
(`break 5d high` best risk-adjusted). Mean ≫ median = right-skewed (typical ~+5%/3mo, a few big
winners). Median dip ~−10% → a stop is mandatory. **Entry/target/stop:** enter on trigger, target
~+20–25% (median peak), stop ~−10%.

**The regime risk:** single, *recovering*-market window. "Buy washouts" + recovery = great; in a
sustained downtrend it catches falling knives and likely flips negative. A sellable product MUST add
a **market-regime filter** (e.g. only fire when DSEX > its 200-day) and say this plainly.

## 4c. Portfolio backtest — "if I invested 1,000" (`scripts/portfolio_backtest.py`)

Event-driven walk-forward: enter washed-out names that trigger (break 5d high) at the close, exit on
stop −10% / target +25% / time 63d, 0.4%/side cost, max 10 concurrent positions, equal-weight.

| | Final (from 1,000) | Total | CAGR | Max DD | Trades | Win% | Avg win / loss |
|---|---|---|---|---|---|---|---|
| **Strategy (no filter)** | **1,337** | **+33.7%** | +15.6% | −20.9% | 138 | 41% | +21.7% / −9.5% |
| Strategy (regime filter) | 1,320 | +32.0% | +14.9% | −21.5% | 74 | 47% | +21.8% / −9.7% |
| Buy & hold DSEX | 1,078 | +7.8% | ~3.8% | −23.3% | — | — | — |

**Reads (honest):**
- Beat the index ~4x on total return (+33.7% vs +7.8%) with slightly *lower* drawdown than the index.
- **Win-rate is only 41%** — most trades lose or stop out. The edge is *asymmetry*: avg win +21.7% vs
  avg loss −9.5% (~2.3:1). Frame for users as "wrong more than half the time, but winners pay for it" —
  psychologically hard; needs discipline to hold the rule.
- **−21% max drawdown** is real — a 1,000 account would have shown ~790 at the worst point.
- **Regime filter (DSEX>50d) didn't help here**: fewer trades (74), better win-rate (47%), but ~same
  return and *slightly worse* drawdown. The 50-day gate trades activity for quality without improving
  the bottom line in this regime. A 200-day gate is untestable (insufficient index history).
- Right-skewed, single-regime, EOD fills, slippage on thin names not modelled → promising, not proof.

## 4d. Robustness sweep — is it curve-fit? (`scripts/robustness.py`)

Vary one knob at a time around the base; the edge must beat the index (+7.8%) across a *range*, not
just at one point. Result: **it does.** Every knob beats the index across essentially its whole range,
and the surface is smooth + directional (the signature of a real effect, not an overfit spike):

- **stop** −6%→−12%: all beat index (+21 to +56 vs index). Only −15% fails (−3). Tighter stops did
  *better* here (sharp-drop regime). Base −10% is conservative.
- **target** +15%→+40%: all beat index (+26 to +58). Lower target best (choppy market → take profit).
- **hold** 40→120d: flat ~+33–44% — not timing-sensitive (good).
- **deep** −30%→−50%: monotonic — deeper washout = better (−50% → +63%). Confirms the core thesis.
- **near_low** 10→25%: all beat index; closest-to-low best (+80% at 10%).
- **max_pos** 5→20: all positive; more positions = higher return + lower drawdown. Concentration (5)
  spikes drawdown to −32% — the strategy needs diversification.

**Verdict:** structural, not curve-fit. The base config is actually *conservative*; deeper-washout /
closer-to-low / more-diversified settings did better. **But** robustness to *parameters* is not
robustness to *regimes* — the whole surface still rests on one recovering-market window. "Deeper =
better" is exactly what would invert in a sustained bear (deepest = falling knife).

## 4e. Scheme lab — entry strategies head-to-head (`scripts/schemes.py`)

A "scheme" = an entry rule. All run through the identical portfolio engine (stop −10% / target +25% /
hold 63d / 10 positions / 0.4% cost) so the leaderboard compares the *entry edge* fairly.

| Scheme | total | CAGR | maxDD | trades | win% | vs index |
|---|---|---|---|---|---|---|
| **1 deep-value reversal** | **+33.7%** | +15.6% | −21% | 138 | 41% | **+25.9** |
| 3 pullback in uptrend | −2.1% | −1.1% | −29% | 95 | 36% | −9.9 |
| 4 near-low reclaim | −4.0% | −2.0% | −28% | 132 | 36% | −11.8 |
| 5 volume breakout (momentum) | −6.1% | −3.1% | −28% | 174 | 33% | −13.9 |
| 2 oversold bounce | −11.8% | −6.1% | −35% | 132 | 34% | −19.6 |

**Verdict: of five price/volume entry rules, only Scheme-1 beat the market — the rest lost money.**
Lessons: (a) the *combination* in Scheme-1 (deep washout + near 52w-low + 5-day-high breakout) is what
works — loosen any leg (Scheme-4) or drop the washout context (Scheme-2, pure oversold = falling
knives) and the edge dies; (b) momentum/breakout (Scheme-5) loses, re-confirming §2. The next frontier
for a *genuinely different* (and diversifying) scheme is **fundamentals — Quality-Value** — a separate
data axis, needs the point-in-time fundamental engine (see §2 method), tracked as a build.

### Scheme lab v2 — hybrids that fuse the proven edges (`scripts/scheme_lab.py`)

Tested more schemes, each with style-appropriate exits on the same engine:

| Scheme | total | CAGR | maxDD | trades | win% | vs index |
|---|---|---|---|---|---|---|
| **3 quality reversal** (washout-bounce + profitable & P/E≤25) | **+73.6%** | **+31.7%** | **−12.1%** | 76 | 58% | **+65.8** |
| 1 deep-value reversal | +33.7% | +15.6% | −20.9% | 138 | 41% | +25.9 |
| 2 quality-value | +30.8% | +14.4% | −13.5% | 30 | 63% | +23.0 |
| 5 magic formula (earnings-yield + ROE) | +7.6% | +3.7% | −19% | 30 | 47% | −0.2 |
| 6 deep growth-value | −0.5% | — | −20% | 40 | 38% | −8.3 |
| 4 cheap + oversold (RSI cross) | −23.6% | — | −33% | 77 | 31% | −31.4 |

**The winner — Scheme-3 "Quality Reversal":** take Scheme-1's washout-bounce **only when the company is
profitable and cheap (P/E≤25)**. That single filter — removing the junk pennies that were Scheme-1's
losers — **doubled the return (+74% vs +34%), halved the drawdown (−12% vs −21%), and lifted win-rate
to 58%.** The two proven edges multiply. Confirmed: price *timing* (deep washout + breakout) is
essential — pure cross-sectional value (5, 6) is mediocre and oversold-timing (4) still catches knives.

**Caveat (multiple comparison):** Scheme-3 is the best of ~10 schemes tried; testing many and picking
the winner inflates apparent performance. The improvement is large and *mechanistically* sensible
(junk removal), not pure noise — but it still needs the same out-of-sample/forward proof as the rest.

### Scheme catalog
- **Scheme-1 — Deep-Value Reversal** ✅ validated. Entry: >40% below 1yr high AND within 15% of 52w
  low AND breaks 5-day high. Exit: stop −10% / target +25% / time 63d. ~2wk–2mo hold. Mean-reversion
  bucket. Result: +34%, 41% win, −21% maxDD, 138 trades.
- **Scheme-2 — Quality-Value** ✅ validated (`scripts/scheme2_value.py`). Monthly: rank profitable
  universe by cheap (P/E, P/B) + quality (ROE, EPS-growth, dividend consistency), buy top-15, exit
  stop −15% / target +50% / hold 180d. Point-in-time fundamentals (fy ≤ year−1). Result: **+31%, 63%
  win, −13.5% maxDD, 30 trades** — nearly Scheme-1's return with HALF the drawdown and a far higher
  win-rate, and it's a *different* edge (fundamentals, long hold) → diversifies Scheme-1. Caveat: only
  30 trades (concentrated hold) → smaller sample than Scheme-1.
- Rejected on this data: oversold-only, near-low-only, pullback-in-uptrend, volume breakout.

### Why combine them (the multi-playbook "Hedge")
Scheme-1 (fast bounces, choppy, high turnover) and Scheme-2 (slow quality holds, smooth, low turnover)
are different edges. Run together: capital stays working (Scheme-2 holds while Scheme-1 waits for
setups), the blended win-rate and drawdown improve, and the daily list draws from both buckets — the
actual product. Next build: a combined portfolio backtest + a unified daily list tagged by scheme.

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
| `scripts/signal_backtest.py` | trigger walk-forward validation (§4b) |
| `scripts/portfolio_backtest.py` | "if I invested 1,000" equity curve (§4c); exposes `simulate()` |
| `scripts/robustness.py` | parameter sensitivity sweep (§4d) |
| `scripts/daily_signals.py` | **live feed** — today's fired signals + watchlist, with entry/stop/target |

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
