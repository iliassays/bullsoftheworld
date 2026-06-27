"""Portfolio backtest — "if I invested 1,000, what happens?" (walk-forward, event-driven).

Simulates the Deep-Value Reversal rule day by day with REAL money mechanics: enter washed-out names
that trigger a turn, exit on stop / target / time, charge transaction costs, cap concurrent positions.
Tracks a daily equity curve, so the output is a P&L you can read — final value, total return, CAGR,
the worst drawdown you'd have stomached, win rate — and the same 1,000 just buying the DSEX index.

    uv run python scripts/portfolio_backtest.py            # no regime filter
    uv run python scripts/portfolio_backtest.py --regime   # only trade when DSEX > its 50-day

Honesty: EOD fills at the close (no intraday), 2-year single recovering-market regime, costs modelled
at 0.4%/side but slippage on thin names is real. This is a historical simulation, not a promise.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict

from sqlalchemy import select

from bulls.core.db import get_sessionmaker
from bulls.core.models import DailyBar, MarketSummary

MARKET = "DSE"
START = 1000.0
MAX_POS = 10  # concurrent positions (diversification)
STOP = -0.10  # exit if it falls 10% from entry
TARGET = 0.25  # exit if it rises 25%
MAX_HOLD = 63  # time exit ~3 months
COST = 0.004  # per side (~0.8% round trip)
WARMUP, MIN_AVG_VOL = 60, 5_000
DEEP, NEAR_LOW = -40.0, 15.0


def _sma(vals, n):
    out, s = [None] * len(vals), 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def _roll(vals, n, fn):
    return [fn(vals[max(0, i - n + 1) : i + 1]) for i in range(len(vals))]


def _roll_extreme(vals, n, want_max):
    """O(n) trailing-window max/min via a monotonic deque (the rolling 52w high/low, fast)."""
    from collections import deque

    dq, out = deque(), [None] * len(vals)
    for i, v in enumerate(vals):
        while dq and ((vals[dq[-1]] <= v) if want_max else (vals[dq[-1]] >= v)):
            dq.pop()
        dq.append(i)
        if dq[0] <= i - n:
            dq.popleft()
        out[i] = vals[dq[0]]
    return out


async def _load():
    sm = get_sessionmaker()
    async with sm() as session:
        bars = list(
            await session.scalars(
                select(DailyBar)
                .where(DailyBar.market == MARKET)
                .order_by(DailyBar.code, DailyBar.date)
            )
        )
        ms = list(
            await session.scalars(select(MarketSummary).where(MarketSummary.market == MARKET))
        )
    by_code = defaultdict(list)
    for b in bars:
        by_code[b.code].append(b)
    dsex = {r.date: r.dsex for r in ms if r.dsex}
    return by_code, dsex


def _signals_by_code(bars, deep, near_low):
    """Dates where this name is in the launch zone AND breaks its 5-day high (the turn trigger)."""
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    hi252 = _roll_extreme(highs, 252, True)
    lo252 = _roll_extreme([b.low for b in bars], 252, False)
    out = set()
    for i in range(WARMUP, len(bars)):
        if not closes[i] or not hi252[i] or hi252[i] <= lo252[i]:
            continue
        below = (closes[i] / hi252[i] - 1) * 100
        pos = (closes[i] - lo252[i]) / (hi252[i] - lo252[i]) * 100
        if below < deep and pos < near_low and closes[i] > max(highs[i - 5 : i]):
            out.add(bars[i].date)
    return out


def _max_drawdown(curve):
    peak, mdd = curve[0][1], 0.0
    for _, eq in curve:
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
    return mdd * 100


def simulate(
    by_code,
    dsex,
    *,
    stop=STOP,
    target=TARGET,
    hold=MAX_HOLD,
    deep=DEEP,
    near_low=NEAR_LOW,
    max_pos=MAX_POS,
    regime=False,
):
    """Run the event-driven sim with the given params. Returns a metrics dict (+ equity curve)."""
    bar_map, sig = {}, {}
    for code, bars in by_code.items():
        if len(bars) < WARMUP + 5 or sum(b.volume for b in bars[-20:]) / 20 < MIN_AVG_VOL:
            continue
        bar_map[code] = {b.date: b for b in bars}
        sig[code] = _signals_by_code(bars, deep, near_low)
    axis = sorted({d for m in bar_map.values() for d in m})
    dts = sorted(dsex)
    dsex_sma = dict(zip(dts, _sma([dsex[d] for d in dts], 50), strict=True))

    cash, positions, curve, trades, trade_log = START, {}, [], [], []
    last_px = {}
    for d in axis:
        for code in list(positions):
            p = positions[code]
            bar = bar_map[code].get(d)
            if bar:
                last_px[code] = bar.close
                p["held"] += 1
                stop_px, tgt_px = p["entry"] * (1 + stop), p["entry"] * (1 + target)
                exit_px, reason = None, ""
                if bar.low <= stop_px:
                    exit_px, reason = stop_px, "stop"  # assume stop hit first (conservative)
                elif bar.high >= tgt_px:
                    exit_px, reason = tgt_px, "target"
                elif p["held"] >= hold:
                    exit_px, reason = bar.close, "time"
                if exit_px is not None:
                    cash += p["shares"] * exit_px * (1 - COST)
                    ret = exit_px / p["entry"] - 1
                    trades.append(ret)
                    trade_log.append({
                        "code": code, "in_date": p["entry_date"], "in_px": p["entry"],
                        "out_date": d, "out_px": round(exit_px, 2), "ret": ret * 100,
                        "held": p["held"], "reason": reason,
                    })
                    del positions[code]

        regime_ok = (not regime) or (
            d in dsex and dsex_sma.get(d) is not None and dsex[d] > dsex_sma[d]
        )
        if regime_ok:
            for code in sorted(c for c in sig if d in sig[c] and c not in positions):
                if len(positions) >= max_pos:
                    break
                bar = bar_map[code].get(d)
                if not bar or not bar.close:
                    continue
                equity = cash + sum(positions[c]["shares"] * last_px.get(c, 0) for c in positions)
                alloc = min(equity / max_pos, cash / (1 + COST))
                if alloc < equity / max_pos * 0.5:
                    continue
                positions[code] = {
                    "shares": alloc / bar.close, "entry": bar.close, "held": 0, "entry_date": d
                }
                cash -= alloc * (1 + COST)
                last_px[code] = bar.close

        equity = cash + sum(positions[c]["shares"] * last_px.get(c, 0) for c in positions)
        curve.append((d, equity))

    final = curve[-1][1]
    years = (axis[-1] - axis[0]).days / 365
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    return {
        "final": final,
        "total": (final / START - 1) * 100,
        "cagr": ((final / START) ** (1 / years) - 1) * 100 if years else 0,
        "maxdd": _max_drawdown(curve),
        "n_trades": len(trades),
        "winrate": len(wins) / len(trades) * 100 if trades else 0,
        "avg_win": sum(wins) / len(wins) * 100 if wins else 0,
        "avg_loss": sum(losses) / len(losses) * 100 if losses else 0,
        "curve": curve,
        "trade_log": trade_log,
    }


async def _run(regime: bool):
    by_code, dsex = await _load()
    m = simulate(by_code, dsex, regime=regime)
    curve, trades_n = m["curve"], m["n_trades"]
    dts = sorted(dsex)
    idx0 = dsex[dts[0]]
    idx_ret = (dsex[dts[-1]] / idx0 - 1) * 100
    idx_curve = [(d, START * dsex[d] / idx0) for d in dts]
    final, cagr = m["final"], m["cagr"]

    tag = "WITH regime filter (DSEX > 50d)" if regime else "NO regime filter"
    print(f"\n===== Deep-Value Reversal — {tag} =====")
    print(f"  Period            {curve[0][0]} → {curve[-1][0]}")
    print(f"  Start             {START:,.0f}")
    print(f"  Final value       {final:,.0f}   ({m['total']:+.1f}%)   CAGR {cagr:+.1f}%")
    print(f"  Max drawdown      {m['maxdd']:.1f}%")
    print(f"  Trades            {trades_n}   win-rate {m['winrate']:.0f}%")
    print(f"  Avg win / loss    {m['avg_win']:+.1f}% / {m['avg_loss']:+.1f}%")
    print("  ---- buy & hold DSEX ----")
    print(
        f"  Final value       {START * (1 + idx_ret / 100):,.0f}   ({idx_ret:+.1f}%)   "
        f"Max drawdown {_max_drawdown(idx_curve):.1f}%"
    )

    print("\n  Equity curve (month-end, strategy vs index):")
    seen = set()
    for d, eq in curve:
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            ix = START * dsex.get(d, idx0) / idx0
            print(f"    {d}  strat {eq:7,.0f}   index {ix:7,.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regime", action="store_true", help="only enter when DSEX > its 50-day SMA")
    asyncio.run(_run(ap.parse_args().regime))


if __name__ == "__main__":
    main()
