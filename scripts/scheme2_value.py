"""Scheme-2 — Quality-Value. Buy cheap AND profitable companies, hold for months.

Cross-sectional + fundamental (unlike the price-only schemes): each month, rank the profitable
universe by cheapness (low P/E, low P/B) and quality (high ROE, growing EPS, pays dividends),
buy the top names, hold long. Fundamentals are point-in-time (fiscal year <= D.year-1, so already
reported — no lookahead). Runs through the same portfolio engine with value-appropriate exits.

    uv run python scripts/scheme2_value.py

Honesty: same 2-year single-regime window; reporting-lag approximation; EOD fills. A *different* edge
from Scheme-1 (works in different conditions) is the point — diversification, not just more return.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

from portfolio_backtest import MIN_AVG_VOL, _load, simulate
from sqlalchemy import select

from bulls.core.db import get_sessionmaker
from bulls.core.models import AnnualFinancial, DividendRecord

REBALANCE = 21  # ~monthly
TOP_N = 15  # how many names rank as "buyable" each rebalance
START_IDX = 80  # let some bar history accrue before first rebalance
# Value-appropriate exits: slower names, give them room and time; let winners run.
STOP, TARGET, HOLD, MAX_POS = -0.15, 0.50, 180, 12


def _pct(pairs, reverse=False):
    if not pairs:
        return {}
    order = sorted(pairs, key=lambda kv: kv[1], reverse=reverse)
    n = len(order)
    return {c: (100.0 if n == 1 else i / (n - 1) * 100) for i, (c, _) in enumerate(order)}


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


async def _load_fundamentals(market):
    sm = get_sessionmaker()
    async with sm() as session:
        fins = list(
            await session.scalars(select(AnnualFinancial).where(AnnualFinancial.market == market))
        )
        divs = list(
            await session.scalars(select(DividendRecord).where(DividendRecord.market == market))
        )
    fin = defaultdict(dict)
    for f in fins:
        fin[f.code][f.fiscal_year] = f
    div = defaultdict(list)
    for d in divs:
        div[d.code].append(d)
    return fin, div


def _fundamentals_at(code, price, year, fin, div):
    """Point-in-time P/E, P/B, ROE, EPS-growth, dividend consistency. None if not profitable/known."""
    fy_years = [y for y in fin.get(code, {}) if y <= year - 1]
    if not fy_years:
        return None
    fy = max(fy_years)
    f = fin[code][fy]
    if not f.eps or f.eps <= 0 or not f.nav_per_share or f.nav_per_share <= 0:
        return None  # Quality-Value requires a profitable company with positive book value
    pe = price / f.eps
    pb = price / f.nav_per_share
    roe = f.eps / f.nav_per_share * 100
    prev = fin[code].get(fy - 1)
    eps_g = (f.eps - prev.eps) / abs(prev.eps) * 100 if prev and prev.eps else None
    consistency = float(
        sum(
            1 for d in div.get(code, []) if d.cash_pct and d.cash_pct > 0 and fy - 5 <= d.year <= fy
        )
    )
    return pe, pb, roe, eps_g, consistency


def _build_signals(by_code, fin, div):
    """For each code, the set of rebalance dates it ranked top-N on Quality-Value (entry signals)."""
    liquid = {
        c: b for c, b in by_code.items() if sum(x.volume for x in b[-20:]) / 20 >= MIN_AVG_VOL
    }
    close_on = {c: {b.date: b.close for b in b_} for c, b_ in liquid.items()}
    axis = sorted({d for b_ in liquid.values() for b in b_ for d in (b.date,)})
    signals = defaultdict(set)
    for k in range(START_IDX, len(axis), REBALANCE):
        d = axis[k]
        rows = {}
        for code in liquid:
            price = close_on[code].get(d)
            if not price:
                continue
            f = _fundamentals_at(code, price, d.year, fin, div)
            if f:
                rows[code] = f
        if len(rows) < 20:
            continue
        pe_r = _pct([(c, v[0]) for c, v in rows.items()], reverse=True)
        pb_r = _pct([(c, v[1]) for c, v in rows.items()], reverse=True)
        roe_r = _pct([(c, v[2]) for c, v in rows.items()])
        eg_r = _pct([(c, v[3]) for c, v in rows.items() if v[3] is not None])
        cons_r = _pct([(c, v[4]) for c, v in rows.items()])
        score = {
            c: _mean(
                [
                    _mean([pe_r.get(c), pb_r.get(c)]),
                    _mean([roe_r.get(c), eg_r.get(c), cons_r.get(c)]),
                ]
            )
            for c in rows
        }
        for code in sorted(score, key=lambda c: score[c], reverse=True)[:TOP_N]:
            signals[code].add(d)
    return signals


async def _run():
    by_code, dsex = await _load()
    fin, div = await _load_fundamentals("DSE")
    signals = _build_signals(by_code, fin, div)
    n_sig = sum(len(v) for v in signals.values())
    print(
        f"Scheme-2 Quality-Value · {len(signals)} names ever ranked top-{TOP_N} · {n_sig} entry signals"
    )
    print(f"Exits: stop {STOP:.0%} / target {TARGET:.0%} / hold {HOLD}d / {MAX_POS} positions\n")

    m = simulate(
        by_code,
        dsex,
        signal_fn=lambda bars: signals.get(bars[0].code, set()),
        stop=STOP,
        target=TARGET,
        hold=HOLD,
        max_pos=MAX_POS,
    )
    dts = sorted(dsex)
    idx_ret = (dsex[dts[-1]] / dsex[dts[0]] - 1) * 100

    print(f"  1,000 -> {m['final']:,.0f}   ({m['total']:+.1f}%)   CAGR {m['cagr']:+.1f}%")
    print(f"  Max drawdown   {m['maxdd']:.1f}%")
    print(
        f"  Trades {m['n_trades']}   win-rate {m['winrate']:.0f}%   avg win/loss +{m['avg_win']:.0f}%/{m['avg_loss']:.0f}%"
    )
    print("  ---- vs ---- ")
    print(f"  Scheme-1 (deep-value reversal): +33.7%   |   buy & hold DSEX: {idx_ret:+.1f}%")

    log = sorted(m["trade_log"], key=lambda t: t["in_date"])
    print("\n  Sample trades:")
    for t in log[:8] + log[-4:]:
        print(
            f"    {t['in_date']!s} bought {t['code']:<11} {t['in_px']:>8.2f}  ->  "
            f"{t['out_date']!s} {t['out_px']:>8.2f}  {t['ret']:+6.1f}%  ({t['reason']}, {t['held']}d)"
        )


if __name__ == "__main__":
    asyncio.run(_run())
