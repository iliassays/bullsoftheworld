"""Factor efficacy study — does each factor actually predict forward returns on DSE?

Reconstructs each factor POINT-IN-TIME at monthly rebalance dates over the bar history, then measures
the Information Coefficient (Spearman rank corr) between the factor and forward 20- and 60-day
returns. Mean IC > 0 = the factor ranked winners; IR = mean/std = how reliably. The output suggests
shortlist weights grounded in evidence, not taste.

    uv run python scripts/factor_study.py

Honesty / limits (read before trusting):
  - 2-year window → ~17 monthly rebalances. Indicative, not gospel; small-sample.
  - Value/quality use a reporting lag (fiscal_year <= year-1) to avoid lookahead — slightly stale.
  - Survivorship: the universe is today's listed names; delisted names are under-represented.
  - FLOW (ownership) is NOT studied: only ~3 shareholding snapshots/stock exist, all recent, so it
    can't be reconstructed historically. It stays a judgment overlay until the weekly scrape
    accumulates monthly history. This study covers value, momentum, quality.
"""

from __future__ import annotations

import asyncio
import bisect
from collections import defaultdict

from sqlalchemy import select

from bulls.analytics import compute
from bulls.core.db import get_sessionmaker
from bulls.core.models import AnnualFinancial, DailyBar, DividendRecord

MARKET = "DSE"
FORWARDS = (20, 60)  # trading-day horizons: ~1mo (swing) and ~3mo (positional/investing)
STEP = 21  # rebalance cadence in trading days (~monthly)
WARMUP = 60  # min bars before a stock is scorable
LOOKBACK = 260  # trailing bars fed to compute() (matches the live analytics step)
FACE_VALUE = 10.0  # DSE par value, for dividend yield = cash% * face / price


def _ranks(vals: list[float]) -> list[float]:
    """Average ranks (1..n), ties shared — the basis for Spearman."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation = Pearson on ranks. None if too few points."""
    if len(xs) < 8:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (vx * vy) if vx and vy else None


def _pct_rank(pairs: list[tuple[str, float]], *, reverse: bool = False) -> dict[str, float]:
    if not pairs:
        return {}
    ordered = sorted(pairs, key=lambda kv: kv[1], reverse=reverse)
    n = len(ordered)
    return {c: (100.0 if n == 1 else i / (n - 1) * 100) for i, (c, _) in enumerate(ordered)}


def _mean(parts: list[float | None]) -> float | None:
    vals = [p for p in parts if p is not None]
    return sum(vals) / len(vals) if vals else None


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
        fins = list(
            await session.scalars(select(AnnualFinancial).where(AnnualFinancial.market == MARKET))
        )
        divs = list(
            await session.scalars(select(DividendRecord).where(DividendRecord.market == MARKET))
        )
    by_code: dict[str, list[DailyBar]] = defaultdict(list)
    for b in bars:
        by_code[b.code].append(b)
    fin_by_code: dict[str, dict[int, AnnualFinancial]] = defaultdict(dict)
    for f in fins:
        fin_by_code[f.code][f.fiscal_year] = f
    div_by_code: dict[str, list[DividendRecord]] = defaultdict(list)
    for d in divs:
        div_by_code[d.code].append(d)
    return by_code, fin_by_code, div_by_code


def _value_quality(code, price, year, fin_by_code, div_by_code):
    """Point-in-time value (pe, pb, yield) and quality (eps growth, dividend consistency)."""
    fins = fin_by_code.get(code, {})
    known = [y for y in fins if y <= year - 1]  # reported by the rebalance date
    pe = pb = yld = eps_g = None
    if known:
        fy = max(known)
        eps, nav = fins[fy].eps, fins[fy].nav_per_share
        if eps and eps > 0:
            pe = price / eps
        if nav and nav > 0:
            pb = price / nav
        if (fy - 1) in fins and fins[fy - 1].eps and eps is not None and fins[fy - 1].eps:
            eps_g = (eps - fins[fy - 1].eps) / abs(fins[fy - 1].eps) * 100
    cash = [
        d for d in div_by_code.get(code, []) if d.cash_pct and d.cash_pct > 0 and d.year <= year - 1
    ]
    if cash:
        latest = max(d.year for d in cash)
        yc = next((d.cash_pct for d in cash if d.year == latest), None)
        if yc and price:
            yld = yc / 100 * FACE_VALUE / price
    consistency = float(sum(1 for d in cash if d.year >= year - 5))
    return pe, pb, yld, eps_g, consistency


def _families_for_date(d_idx, axis, by_code, fin_by_code, div_by_code):
    """Build value/momentum/quality composite scores + forward returns for the cross-section at d_idx."""
    d = axis[d_idx]
    raw: dict[str, dict] = {}
    for code, bars in by_code.items():
        dates = [b.date for b in bars]
        i = bisect.bisect_right(dates, d) - 1
        if i < WARMUP or dates[i] != d:  # must trade on d and have warmup history
            continue
        res = compute(bars[max(0, i - LOOKBACK + 1) : i + 1])
        price = res.last_close
        pe, pb, yld, eps_g, consistency = _value_quality(
            code, price, d.year, fin_by_code, div_by_code
        )
        raw[code] = {
            "price": price,
            "trend": 50 * (res.above_sma_50 or 0) + 50 * (res.above_sma_200 or 0),
            "cmf": res.cmf_20,
            "relvol": min(res.relative_volume, 5) if res.relative_volume else None,
            "rsi": res.rsi_14,
            "pe": pe,
            "pb": pb,
            "yld": yld,
            "eps_g": eps_g,
            "consistency": consistency,
        }
    if len(raw) < 20:
        return None

    def rank(key, reverse=False):
        return _pct_rank(
            [(c, v[key]) for c, v in raw.items() if v[key] is not None], reverse=reverse
        )

    pe_r, pb_r, yld_r = rank("pe", reverse=True), rank("pb", reverse=True), rank("yld")
    cmf_r, relvol_r, rsi_r = rank("cmf"), rank("relvol"), rank("rsi")
    epsg_r, cons_r = rank("eps_g"), rank("consistency")

    out = {}
    for c, v in raw.items():
        out[c] = {
            "value": _mean([pe_r.get(c), pb_r.get(c), yld_r.get(c)]),
            "momentum": _mean([v["trend"], cmf_r.get(c), relvol_r.get(c), rsi_r.get(c)]),
            "quality": _mean([epsg_r.get(c), cons_r.get(c)]),
            "price": v["price"],
        }
    return out


def _fwd_returns(d_idx, fwd, axis, by_code, codes):
    """Forward return per code from axis[d_idx] to axis[d_idx+fwd], on the market date axis."""
    d, df = axis[d_idx], axis[d_idx + fwd]
    out = {}
    for code in codes:
        bars = by_code[code]
        dates = [b.date for b in bars]
        i = bisect.bisect_right(dates, d) - 1
        j = bisect.bisect_right(dates, df) - 1
        if i >= 0 and j > i and dates[i] == d:
            p0, p1 = bars[i].close, bars[j].close
            if p0 > 0:
                out[code] = (p1 / p0 - 1) * 100
    return out


async def _run():
    by_code, fin_by_code, div_by_code = await _load()
    axis = sorted({b.date for bars in by_code.values() for b in bars})
    n = len(axis)
    max_fwd = max(FORWARDS)
    rebal = list(range(WARMUP, n - max_fwd, STEP))
    print(
        f"Universe {len(by_code)} codes · {n} trading days · {len(rebal)} monthly rebalances "
        f"({axis[rebal[0]]} → {axis[rebal[-1]]})"
    )

    # ic[family][fwd] = list of per-date ICs
    ic: dict[str, dict[int, list[float]]] = {
        f: {h: [] for h in FORWARDS} for f in ("value", "momentum", "quality")
    }
    for d_idx in rebal:
        fam = _families_for_date(d_idx, axis, by_code, fin_by_code, div_by_code)
        if not fam:
            continue
        codes = list(fam)
        for fwd in FORWARDS:
            rets = _fwd_returns(d_idx, fwd, axis, by_code, codes)
            shared = [c for c in codes if c in rets]
            for family in ic:
                xs = [fam[c][family] for c in shared if fam[c][family] is not None]
                ys = [rets[c] for c in shared if fam[c][family] is not None]
                r = _spearman(xs, ys)
                if r is not None:
                    ic[family][fwd].append(r)

    print(
        f"\n{'FACTOR':<10}", *[f"{'IC@' + str(h) + 'd':>9}{'IR':>7}{'hit%':>6}" for h in FORWARDS]
    )
    print("-" * 60)
    suggest: dict[int, dict[str, float]] = {h: {} for h in FORWARDS}
    for family, per in ic.items():
        cells = []
        for h in FORWARDS:
            arr = per[h]
            if arr:
                mean = sum(arr) / len(arr)
                std = (sum((x - mean) ** 2 for x in arr) / len(arr)) ** 0.5
                ir = mean / std if std else 0.0
                hit = sum(1 for x in arr if x > 0) / len(arr) * 100
                cells.append(f"{mean:>+9.3f}{ir:>7.2f}{hit:>5.0f}%")
                suggest[h][family] = max(0.0, mean)
            else:
                cells.append(f"{'·':>9}{'·':>7}{'·':>6}")
        print(f"{family:<10}", *cells)

    print(
        "\nData-suggested family weights (∝ positive mean IC, renormalized; flow added as overlay):"
    )
    for h, label in ((20, "swing/short"), (60, "positional/investing")):
        tot = sum(suggest[h].values())
        if tot:
            w = {f: round(v / tot, 2) for f, v in suggest[h].items()}
            print(f"  {label:<22} {w}")
    print(
        "\nNote: flow not calibrated here (insufficient ownership history) — keep it a modest manual overlay."
    )


if __name__ == "__main__":
    asyncio.run(_run())
