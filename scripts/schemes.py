"""Scheme lab — test different entry strategies head-to-head on the same engine.

A "scheme" is just an entry rule (when to buy). Each runs through the identical portfolio simulator
(same stop/target/hold/cost/position-cap) so the leaderboard compares the ENTRY edge fairly. Goal:
find schemes that beat Scheme-1 (Deep-Value Reversal). Price/volume schemes only here — a
fundamentals scheme (Quality-Value) needs the point-in-time fundamental engine, tracked separately.

    uv run python scripts/schemes.py
"""

from __future__ import annotations

import asyncio
from collections import deque

from portfolio_backtest import WARMUP, _load, dsex_return, simulate


def _sma(vals, n):
    out, s = [None] * len(vals), 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def _rsi(closes, n=14):
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    g = sum(max(closes[i] - closes[i - 1], 0) for i in range(1, n + 1)) / n
    loss = sum(max(closes[i - 1] - closes[i], 0) for i in range(1, n + 1)) / n
    out[n] = 100 - 100 / (1 + g / loss) if loss else 100.0
    for i in range(n + 1, len(closes)):
        ch = closes[i] - closes[i - 1]
        g = (g * (n - 1) + max(ch, 0)) / n
        loss = (loss * (n - 1) + max(-ch, 0)) / n
        out[i] = 100 - 100 / (1 + g / loss) if loss else 100.0
    return out


def _roll_ext(vals, n, want_max):
    dq, out = deque(), [None] * len(vals)
    for i, v in enumerate(vals):
        while dq and ((vals[dq[-1]] <= v) if want_max else (vals[dq[-1]] >= v)):
            dq.pop()
        dq.append(i)
        if dq[0] <= i - n:
            dq.popleft()
        out[i] = vals[dq[0]]
    return out


def _prep(bars):
    c = [b.close for b in bars]
    h = [b.high for b in bars]
    v = [float(b.volume) for b in bars]
    return (
        c,
        h,
        _rsi(c),
        _sma(c, 20),
        _sma(c, 200),
        _sma(v, 20),
        _roll_ext(h, 252, True),
        _roll_ext([b.low for b in bars], 252, False),
    )


def deep_value_reversal(bars):
    """Scheme-1: deep washout (>40% below 1yr high), near 52w low, breaks 5-day high."""
    c, h, _r, _s20, _s200, _v20, hi, lo = _prep(bars)
    out = set()
    for i in range(WARMUP, len(bars)):
        if not c[i] or not hi[i] or hi[i] <= lo[i]:
            continue
        below = (c[i] / hi[i] - 1) * 100
        pos = (c[i] - lo[i]) / (hi[i] - lo[i]) * 100
        if below < -40 and pos < 15 and c[i] > max(h[i - 5 : i]):
            out.add(bars[i].date)
    return out


def oversold_bounce(bars):
    """Scheme-2: RSI crosses up through 30 (pure oversold reversal, anywhere)."""
    _c, _h, rsi, *_ = _prep(bars)
    return {
        bars[i].date
        for i in range(WARMUP, len(bars))
        if rsi[i - 1] is not None and rsi[i] is not None and rsi[i - 1] < 30 <= rsi[i]
    }


def pullback_uptrend(bars):
    """Scheme-3: strong name (above 200d) pulls back to the 20d, then reclaims it."""
    c, _h, rsi, s20, s200, *_ = _prep(bars)
    out = set()
    for i in range(WARMUP, len(bars)):
        if not (s200[i] and s20[i] and s20[i - 1] and rsi[i] is not None):
            continue
        if c[i] > s200[i] and c[i - 1] <= s20[i - 1] and c[i] > s20[i] and rsi[i] < 60:
            out.add(bars[i].date)
    return out


def near_low_reclaim(bars):
    """Scheme-4: near 52w low (looser, <25%) + breaks its 3-day high (early reversal)."""
    c, h, _rsi, _s20, _s200, _v20, hi, lo = _prep(bars)
    out = set()
    for i in range(WARMUP, len(bars)):
        if not hi[i] or hi[i] <= lo[i]:
            continue
        pos = (c[i] - lo[i]) / (hi[i] - lo[i]) * 100
        if pos < 25 and c[i] > max(h[i - 3 : i]):
            out.add(bars[i].date)
    return out


def volume_breakout(bars):
    """Scheme-5: breaks 20-day high on >1.5x average volume (momentum breakout — the contrast)."""
    _c, h, _r, _s20, _s200, v20, *_ = _prep(bars)
    cl = [b.close for b in bars]
    v = [float(b.volume) for b in bars]
    out = set()
    for i in range(WARMUP, len(bars)):
        if v20[i] and cl[i] > max(h[i - 20 : i]) and v[i] > 1.5 * v20[i]:
            out.add(bars[i].date)
    return out


SCHEMES = {
    "1 deep-value reversal": deep_value_reversal,
    "2 oversold bounce": oversold_bounce,
    "3 pullback in uptrend": pullback_uptrend,
    "4 near-low reclaim": near_low_reclaim,
    "5 volume breakout": volume_breakout,
}


async def _run():
    by_code, dsex = await _load()
    index_return = dsex_return(dsex)
    print("Same engine for all (stop -10% / target +25% / hold 63d / 10 positions / 0.4% cost).")
    print(f"Reference — full-window DSEX price return: {index_return:+.1f}%\n")
    print(
        f"{'SCHEME':<24}{'total%':>9}{'CAGR%':>8}{'maxDD%':>9}{'trades':>8}{'win%':>7}{'avg W/L':>12}{'vs index':>10}"
    )
    print("-" * 88)
    rows = []
    for name, fn in SCHEMES.items():
        m = simulate(by_code, dsex, signal_fn=fn)
        rows.append((name, m))
    for name, m in sorted(rows, key=lambda r: r[1]["total"], reverse=True):
        wl = f"+{m['avg_win']:.0f}/{m['avg_loss']:.0f}"
        print(
            f"{name:<24}{m['total']:>+9.1f}{m['cagr']:>+8.1f}{m['maxdd']:>9.1f}"
            f"{m['n_trades']:>8}{m['winrate']:>6.0f}%{wl:>12}{m['total'] - index_return:>+10.1f}"
        )


if __name__ == "__main__":
    asyncio.run(_run())
