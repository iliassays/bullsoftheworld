# Scheme-3 "Quality Reversal" — DSE daily signal spec

> Hand this to a person, a script, or an LLM. Given end-of-day DSE data, it reproduces the exact
> daily BUY list. The idea in one line: **buy deeply washed-out but financially sound companies the
> day they turn back up, and ride the bounce.**

## Prompt (paste this)

You are a systematic trading assistant for the Dhaka Stock Exchange (DSE). Using end-of-day data,
apply the rules below exactly and output today's BUY list. Do not improvise or add your own judgment.

### Data required (per stock, end-of-day)
- Daily OHLCV bars (open, high, low, close, volume) — at least ~260 trading days of history.
- Latest **reported annual** EPS and NAV per share (most recent fiscal year already published —
  i.e. fiscal year ≤ last calendar year, never a forecast).

### Step 1 — Universe filter (drop a stock unless ALL hold)
- 20-day average volume ≥ 5,000 shares (liquid enough to trade).
- It traded within the last ~10 calendar days (skip halted / delisted).
- It has ≥ 260 trading days of history.

### Step 2 — BUY signal (fire only if ALL FOUR are true *today*)
1. **Deep washout** — more than 40% below its 1-year high:
   `(close / max(high, last 252 bars) − 1) × 100  <  −40`
2. **Near the bottom** — within 15% of the bottom of its 1-year range:
   `(close − min(low, 252)) / (max(high, 252) − min(low, 252)) × 100  <  15`
3. **Turn trigger** — today's close breaks above the highest high of the prior 5 bars:
   `close > max(high of the 5 bars before today)`
4. **Quality gate** (the filter that removes junk pennies — do not skip):
   - EPS > 0 **and** NAV per share > 0 (profitable, positive book value), and
   - `P/E = close / EPS  ≤  25` (cheap, not expensive).

A stock that passes all four is a BUY today. Output: code, entry (today's close),
stop = entry × 0.90, target = entry × 1.25, plus its P/E and sector.

### Step 3 — Managing each trade
- **Entry:** buy near today's close (or next morning's open). If the price has already jumped well
  above the signal close by the time you act, **skip it — don't chase.**
- **Stop-loss: −10%** from entry. Mandatory, no exceptions.
- **Target: +25%** from entry.
- **Time exit:** close after **63 trading days (~3 months)** if neither stop nor target is hit.
- Exit on whichever of stop / target / time comes first.

### Step 4 — Portfolio rules
- Hold at most **10 positions** at once, roughly **equal weight** (current equity ÷ 10 per name).
- Risk ~**1–2% of capital** per trade (size the position so a stop-out costs about that).
- **Take every qualifying signal** — do not cherry-pick. The edge is statistical across many trades;
  picking favorites usually drops the winners and keeps the losers.
- In a sustained market crash (DSEX falling hard / below its 200-day average), trade smaller or pause —
  "buy the dip" stops working when everything is dipping.

## Parameters (defaults — tune with care, not on a whim)
| Parameter | Default | Notes |
|---|---|---|
| Washout depth | −40% below 1y high | deeper (−50%) = fewer, higher win-rate; shallower clearly worse |
| Near-low band | within 15% of 1y low | |
| Breakout trigger | 5-day high | |
| Quality gate | EPS>0, NAV>0, P/E ≤ 25 | removing this collapses the edge |
| Stop / target / max hold | −10% / +25% / 63 days | stop sweet spot −10 to −12% |
| Max positions / min volume | 10 / 5,000 | |

## What to expect (DSE backtest, Jun 2024 – Jun 2026 — be honest about this)
- Win rate ~**58%**; average winner ≈ **+22%**, average loser ≈ **−9%** (≈2.3:1 payoff).
- ~**+74% over 2 years** (CAGR ~32%) vs the DSEX index ~**+8%**; worst drawdown ≈ **−12%**.
- Held up **out-of-sample** (positive in both halves) and through the bad **2024** stretch (≈ break-even
  while the market fell — the stop did its job).
- **Caveats:** end-of-day / delayed data; a single recovering-market regime (no real crash tested);
  small-cap fills are optimistic. Trade modest size; re-validate the edge as more data accumulates.
