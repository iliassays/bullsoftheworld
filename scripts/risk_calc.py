"""Risk calculator + position sizer for Scheme-3 (DSE) — sized to YOUR portfolio.

First analyses the data to justify the risk model (how reliable the -10% stop is, the trade-loss
distribution, how many positions the strategy actually runs at once), then sizes today's live signals
for a given capital using fixed-fractional risk + diversification caps. Count-independent: each trade
is sized by risk, so it works whether 3 or 10 names fire.

    uv run python scripts/risk_calc.py                  # 200,000 BDT, 1% risk/trade
    uv run python scripts/risk_calc.py --capital 500000 --risk 0.75
"""

from __future__ import annotations

import argparse
import asyncio

from hedge_daily import scan
from portfolio_backtest import _load, simulate
from scheme2_value import _load_fundamentals
from scheme_lab import quality_reversal

STOP_PCT, TARGET_PCT = 0.10, 0.25  # Scheme-3 exits
MAX_POSITIONS = 10
MAX_POSITION_PCT = 15.0  # no single name above this % of the portfolio
MAX_HEAT_PCT = 12.0  # total capital "at risk" across all open positions


async def analyze():
    by_code, dsex = await _load()
    fin, div = await _load_fundamentals("DSE")
    sigs = quality_reversal(by_code, fin, div)
    m = simulate(
        by_code,
        dsex,
        signal_fn=lambda b: sigs.get(b[0].code, set()),
        stop=-STOP_PCT,
        target=TARGET_PCT,
        hold=63,
        max_pos=MAX_POSITIONS,
    )
    tl = m["trade_log"]
    losses = [t["ret"] for t in tl if t["ret"] <= 0]
    worst = min(t["ret"] for t in tl)
    beyond = sum(1 for t in tl if t["ret"] < -10.5)  # losses worse than the -10% stop (gap-through)

    # max simultaneous open positions across the backtest
    ev = []
    for t in tl:
        ev.append((t["in_date"], 1))
        ev.append((t["out_date"], -1))
    ev.sort()
    cur = mx = 0
    for _, d in ev:
        cur += d
        mx = max(mx, cur)

    # DSE circuit-breaker check: how often does a stock fall >10% in one day? (stop reliability)
    drops = total = 0
    for bb in by_code.values():
        for i in range(1, len(bb)):
            if bb[i - 1].close:
                total += 1
                if bb[i].close / bb[i - 1].close - 1 < -STOP_PCT:
                    drops += 1
    return {
        "n": len(tl),
        "worst": worst,
        "beyond": beyond,
        "n_loss": len(losses),
        "maxdd": m["maxdd"],
        "max_concurrent": mx,
        "drop_rate": drops / total * 100,
    }


def size(capital, risk_pct, signals):
    risk_bdt = risk_pct / 100 * capital
    rows, invested, heat = [], 0.0, 0.0
    for s in signals:
        if len(rows) >= MAX_POSITIONS or heat + risk_bdt > MAX_HEAT_PCT / 100 * capital + 1:
            break
        e, stop, tgt = s["price"], s["stop"], s["target"]
        pos_value = min(risk_bdt / STOP_PCT, MAX_POSITION_PCT / 100 * capital, capital - invested)
        shares = int(pos_value // e)
        if shares <= 0:
            continue
        inv = shares * e
        rsk = shares * (e - stop)
        rows.append(
            {
                "code": s["code"],
                "entry": e,
                "stop": stop,
                "target": tgt,
                "shares": shares,
                "invested": inv,
                "risk": rsk,
                "reward": shares * (tgt - e),
            }
        )
        invested += inv
        heat += rsk
    return rows, invested, heat


async def _run(capital, risk_pct):
    a = await analyze()
    print("=== DATA ANALYSIS (why these numbers) ===")
    print(f"  DSE single-day drops worse than -10%: {a['drop_rate']:.2f}% of all days")
    print(
        "    -> the ~10% circuit breaker makes the -10% stop RELIABLE (you rarely gap through it)."
    )
    print(
        f"  Scheme-3 trades: {a['n']} · losses worse than the -10% stop: {a['beyond']} "
        f"(worst single trade {a['worst']:.0f}%)"
    )
    print(
        f"  Most positions open at once (backtest): {a['max_concurrent']} · portfolio max drawdown {a['maxdd']:.0f}%"
    )
    print(
        f"\n  => Model: risk a fixed {risk_pct:.2f}% of capital per trade. With a 10% stop, that means"
    )
    print(
        f"     each position = {risk_pct * 10:.0f}% of the portfolio; cap at {MAX_POSITIONS} names / "
        f"{MAX_HEAT_PCT:.0f}% total at-risk.\n"
    )

    d = await scan(days=10)
    rows, invested, heat = size(capital, risk_pct, d["fired"])
    print(
        f"=== POSITION SIZING — capital {capital:,.0f} BDT · risk {risk_pct:.2f}%/trade · {len(rows)} signals ==="
    )
    print(
        f"  {'CODE':<11}{'entry':>8}{'stop':>8}{'target':>8}{'shares':>8}{'invest':>11}{'risk':>9}{'reward':>9}"
    )
    for r in rows:
        print(
            f"  {r['code']:<11}{r['entry']:>8.1f}{r['stop']:>8.1f}{r['target']:>8.1f}"
            f"{r['shares']:>8,}{r['invested']:>11,.0f}{r['risk']:>9,.0f}{r['reward']:>9,.0f}"
        )
    pct = lambda x: x / capital * 100  # noqa: E731
    print(
        f"\n  Invested: {invested:,.0f} BDT ({pct(invested):.0f}%)  ·  Cash: {capital - invested:,.0f} BDT"
    )
    print(
        f"  Total at risk (heat): {heat:,.0f} BDT ({pct(heat):.1f}%)  <- max loss if EVERY open trade stops out"
    )

    print("\n=== HOW MANY NAMES? (risk% sets it automatically — you don't have to guess) ===")
    print(f"  {'risk/trade':>11}{'position size':>15}{'max names':>11}{'portfolio max loss':>20}")
    for rp in (0.5, 1.0, 1.5, 2.0):
        n = min(MAX_POSITIONS, int(MAX_HEAT_PCT / rp))
        print(f"  {rp:>10.2f}%{rp * 10:>13.0f}%{n:>11}{n * rp:>18.0f}%")
    print(
        "\n  Lower risk% = smaller positions = MORE names (more diversification). The position cap"
    )
    print(
        "  (15%/name) and heat cap (12%) mean you're never over-exposed, no matter how many fire."
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--capital", type=float, default=200_000)
    p.add_argument("--risk", type=float, default=1.0, help="percent of capital risked per trade")
    a = p.parse_args()
    asyncio.run(_run(a.capital, a.risk))


if __name__ == "__main__":
    main()
