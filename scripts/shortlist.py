"""Personal buy/sell shortlist — a ranked, reasoned candidate list for DSE (EOD decision support).

NOT the public portal (which is descriptive-only). This is your own tool: it scores the whole
universe across four factor families, blends them per horizon, and prints a ranked shortlist with
the *why* and the key levels behind each name.

    uv run python scripts/shortlist.py                 # all horizons, top 15 each
    uv run python scripts/shortlist.py --horizon swing --top 25
    uv run python scripts/shortlist.py --code GP       # explain one name's score

Data is end-of-day/delayed. This ranks candidates and entry context; you place the orders.
v1 weights are transparent starters — phase 2 calibrates them from the 2-year history.
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import func, select

from bulls.core.db import get_sessionmaker
from bulls.core.models import CompanyProfile, DividendRecord, Symbol, TickerAnalytics

MARKET = "DSE"
MIN_AVG_VOLUME = 5_000  # drop near-untradeable names so the list is actionable

# Horizon = a weighting of the four family scores (each 0-100). Sums to 1.0.
HORIZONS: dict[str, dict[str, float]] = {
    "swing": {"momentum": 0.45, "flow": 0.30, "value": 0.10, "quality": 0.15},
    "positional": {"momentum": 0.30, "flow": 0.25, "value": 0.25, "quality": 0.20},
    "investing": {"value": 0.40, "quality": 0.35, "flow": 0.15, "momentum": 0.10},
}


def _pct_rank(values: dict[str, float], *, reverse: bool = False) -> dict[str, float]:
    """Cross-sectional percentile rank (0-100) over non-null values. reverse=True → lower is better."""
    present = {c: v for c, v in values.items() if v is not None}
    if not present:
        return {}
    ordered = sorted(present.items(), key=lambda kv: kv[1], reverse=reverse)
    n = len(ordered)
    return {
        c: (100.0 if n == 1 else round(i / (n - 1) * 100, 1)) for i, (c, _) in enumerate(ordered)
    }


def _mean(parts: list[float | None]) -> float | None:
    vals = [p for p in parts if p is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


class Row:
    """A symbol's analytics + profile, flattened for scoring."""

    def __init__(
        self, a: TickerAnalytics, sym: Symbol, prof: CompanyProfile | None, div_years: int
    ):
        self.code = a.code
        self.name = sym.name_en
        self.sector = sym.sector or (prof.sector if prof else None)
        self.close = a.last_close
        self.a = a
        self.prof = prof
        self.div_years = div_years
        # leverage ratio: long-term debt / market cap (lower = better); None if not computable
        self.debt_ratio = (
            prof.long_term_loan_mn / a.market_cap_mn
            if prof and prof.long_term_loan_mn and a.market_cap_mn
            else None
        )


async def _load_rows() -> list[Row]:
    sm = get_sessionmaker()
    async with sm() as session:
        analytics = {
            a.code: a
            for a in await session.scalars(
                select(TickerAnalytics).where(TickerAnalytics.market == MARKET)
            )
        }
        symbols = {
            s.code: s for s in await session.scalars(select(Symbol).where(Symbol.market == MARKET))
        }
        profiles = {
            p.code: p
            for p in await session.scalars(
                select(CompanyProfile).where(CompanyProfile.market == MARKET)
            )
        }
        # dividend consistency: count of recent years with a cash dividend
        div_rows = await session.execute(
            select(DividendRecord.code, func.count())
            .where(
                DividendRecord.market == MARKET,
                DividendRecord.cash_pct > 0,
                DividendRecord.year >= 2020,
            )
            .group_by(DividendRecord.code)
        )
        div_years = dict(div_rows.all())

    rows: list[Row] = []
    for code, a in analytics.items():
        sym = symbols.get(code)
        if not sym or sym.is_hidden or not sym.is_active:
            continue
        if (a.avg_volume_20 or 0) < MIN_AVG_VOLUME:  # illiquid → not actionable
            continue
        rows.append(Row(a, sym, profiles.get(code), div_years.get(code, 0)))
    return rows


def _score(rows: list[Row]) -> dict[str, dict[str, float | None]]:
    """Compute the four family sub-scores (0-100) for every row, cross-sectionally."""
    g = lambda attr: {r.code: getattr(r.a, attr) for r in rows}  # noqa: E731

    # --- Value: cheaper = higher score ---
    pe = _pct_rank(g("pe_ratio"), reverse=True)
    pb = _pct_rank(g("pb_ratio"), reverse=True)
    yld = _pct_rank(g("dividend_yield"))
    pe_sec = _pct_rank(g("pe_vs_sector"), reverse=True)

    # --- Momentum/trend: in-trend, accumulating, participated ---
    trend = {r.code: (50 * (r.a.above_sma_50 or 0) + 50 * (r.a.above_sma_200 or 0)) for r in rows}
    cmf = _pct_rank(g("cmf_20"))
    relvol = _pct_rank(
        {r.code: min(r.a.relative_volume, 5) if r.a.relative_volume else None for r in rows}
    )
    rsi = _pct_rank({r.code: r.a.rsi_14 for r in rows})

    # --- Ownership flow: smart money adding ---
    inst_d = _pct_rank(g("institute_delta"))
    fgn_d = _pct_rank(g("foreign_delta"))

    # --- Quality: growing, pays, low debt ---
    eps_g = _pct_rank(g("eps_growth_yoy"))
    consistency = _pct_rank({r.code: float(r.div_years) for r in rows})
    low_debt = _pct_rank({r.code: r.debt_ratio for r in rows}, reverse=True)

    out: dict[str, dict[str, float | None]] = {}
    for r in rows:
        c = r.code
        out[c] = {
            "value": _mean([pe.get(c), pb.get(c), yld.get(c), pe_sec.get(c)]),
            "momentum": _mean([trend.get(c), cmf.get(c), relvol.get(c), rsi.get(c)]),
            "flow": _mean([inst_d.get(c), fgn_d.get(c), cmf.get(c)]),
            "quality": _mean([eps_g.get(c), consistency.get(c), low_debt.get(c)]),
        }
    return out


def _composite(sub: dict[str, float | None], weights: dict[str, float]) -> float:
    """Weighted blend of family scores, renormalized over the families that are present."""
    num = sum(weights[f] * s for f, s in sub.items() if s is not None)
    den = sum(weights[f] for f, s in sub.items() if s is not None)
    return round(num / den, 1) if den else 0.0


def _reasons(r: Row, sub: dict[str, float | None]) -> str:
    bits: list[str] = []
    a = r.prof
    if r.a.pe_vs_sector is not None and r.a.pe_vs_sector < 0.8:
        bits.append(f"cheap vs sector ({r.a.pe_vs_sector}x median)")
    if r.a.dividend_yield and r.a.dividend_yield >= 4:
        bits.append(f"yield {r.a.dividend_yield}%")
    if (r.a.institute_delta or 0) > 0.1 or (r.a.foreign_delta or 0) > 0.1:
        bits.append(f"smart money adding (inst {r.a.institute_delta:+}, fgn {r.a.foreign_delta:+})")
    if r.a.above_sma_50 and r.a.above_sma_200:
        bits.append("above 50/200-day")
    if (r.a.cmf_20 or 0) > 0.05:
        bits.append(f"accumulation (CMF {r.a.cmf_20})")
    if r.a.eps_growth_yoy and r.a.eps_growth_yoy > 15:
        bits.append(f"EPS +{r.a.eps_growth_yoy}% YoY")
    if r.a.rsi_14 and r.a.rsi_14 > 72:
        bits.append(f"⚠ overbought (RSI {r.a.rsi_14})")
    if a and a.long_term_loan_mn == 0:
        bits.append("debt-free")
    return "; ".join(bits) or "balanced profile"


def _print_horizon(name: str, rows: list[Row], scores: dict, top: int) -> None:
    weights = HORIZONS[name]
    ranked = sorted(rows, key=lambda r: _composite(scores[r.code], weights), reverse=True)[:top]
    print(f"\n{'=' * 100}\n  {name.upper()}  (weights: {weights})\n{'=' * 100}")
    print(
        f"  {'#':>2} {'CODE':<12}{'SCORE':>6}  {'V':>4}{'M':>4}{'F':>4}{'Q':>4}  {'CLOSE':>8}  WHY"
    )
    for i, r in enumerate(ranked, 1):
        s = scores[r.code]
        comp = _composite(s, weights)
        sv = lambda x: f"{x:>4.0f}" if x is not None else "   ·"  # noqa: E731
        print(
            f"  {i:>2} {r.code:<12}{comp:>6.1f}  {sv(s['value'])}{sv(s['momentum'])}{sv(s['flow'])}{sv(s['quality'])}"
            f"  {r.close:>8.2f}  {_reasons(r, s)[:70]}"
        )


def _print_one(code: str, rows: list[Row], scores: dict) -> None:
    r = next((r for r in rows if r.code == code.upper()), None)
    if not r:
        print(f"{code}: not in the actionable universe (illiquid/hidden, or no analytics).")
        return
    s = scores[r.code]
    print(f"\n  {r.code} — {r.name}  [{r.sector}]   close {r.close}")
    print(
        f"  family scores: value={s['value']} momentum={s['momentum']} flow={s['flow']} quality={s['quality']}"
    )
    for h, w in HORIZONS.items():
        print(f"    {h:<11} composite {_composite(s, w):>5}")
    a = r.a
    print(
        f"  levels: support {a.nearest_support}  resistance {a.nearest_resistance}  "
        f"52w {a.week52_low}-{a.week52_high}  RSI {a.rsi_14}  ATR {a.atr_14}"
    )
    print(f"  why: {_reasons(r, s)}")


async def _run(args) -> None:
    rows = await _load_rows()
    scores = _score(rows)
    print(f"\nUniverse: {len(rows)} actionable DSE names (as of latest EOD). EOD/delayed data.")
    if args.code:
        _print_one(args.code, rows, scores)
        return
    horizons = [args.horizon] if args.horizon != "all" else list(HORIZONS)
    for h in horizons:
        _print_horizon(h, rows, scores, args.top)
    print(
        "\nLegend: V=value M=momentum F=flow Q=quality (0-100 percentile). Starter weights — calibrate in phase 2."
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Ranked DSE buy/sell shortlist (EOD decision support).")
    p.add_argument("--horizon", choices=[*HORIZONS, "all"], default="all")
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--code", help="explain one symbol's score instead of ranking")
    asyncio.run(_run(p.parse_args()))


if __name__ == "__main__":
    main()
