"""Scanner — the "hunt with the data" surface that replaces the passive Watchlist tab.

Two retail-facing tabs, assembled from boards:
- **Today** — Quality Reversal (the research flagship) and Active Today (validated EOD trending).
- **Value** — Value + Quality and Dividend.

The Scanner is intentionally narrower than the Market page: it keeps setup boards visible even when
empty, adds verification context, and avoids generic dashboard lists as primary boards. `?watched=true`
scopes every board to the caller's watchlist. Descriptive, liquidity-gated, freshness-stamped — never
advice.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from api.deps import CurrentTenant, DbSession, OptionalUser, enforce_market_feature
from api.routers.screener import ScreenItem, ScreenOut, _enrich
from bulls.analytics import buffett_quality_score, graham_score, smart_money_score
from bulls.core.models import (
    DailyBar,
    MarketSummary,
    QuoteSnapshot,
    Symbol,
    TickerAnalytics,
    TrendingScore,
    WatchlistItem,
)

router = APIRouter(tags=["scanner"])

# Reuse the screener's liquidity gate (see spec §0.9 — this constant should eventually be shared).
_MIN_ADTV_MN = 5.0
_MIN_MCAP_MN = 500.0
_MIN_FREE_FLOAT_CAP_MN = 100.0

# Quality Reversal thresholds (from dse-trading-research.md Scheme-3).
_WASHOUT_FROM_HIGH = -40.0  # >=40% off the 52-week high
_NEAR_LOW = 15.0  # still within 15% of the 52-week low
_MAX_PE = 25.0  # reasonably priced
_5D = 5  # prior-day window for the breakout trigger

# Oversold Quality (from dse-trading-research.md §2 — oversold RSI was the strongest single
# signal: IC +0.094 @60d, positive on 82% of rebalances; quality filter per the Scheme-3 lesson).
_OVERSOLD_RSI = 30.0

# Truth-in-labeling per board (spec review 2026-07-02): what each list's evidence actually is.
_EVIDENCE: dict[str, str] = {
    "quality_reversal": "backtested",
    "oversold_quality": "backtested",
    "active_today": "backtested",
    "most_active": "utility",
    "value_quality": "utility",
    "dividend_quality": "utility",
    "lens_agreement": "framework",
    "lens_buffett_quality": "framework",
    "lens_graham_value": "framework",
    "lens_smart_money": "framework",
    "lens_risk_control": "framework",
}

# The reversal-family edge is regime-dependent: proven on a *recovering* market, likely a
# falling-knife catcher in a sustained bear. These boards get the live regime banner.
_REGIME_SENSITIVE = frozenset({"quality_reversal", "oversold_quality"})
_REGIME_WINDOW = 200
_REGIME_MIN_OBS = 120  # under this, say nothing (omit over mislead)


def regime_from(latest: float, avg: float) -> str:
    return "above_200dma" if latest >= avg else "below_200dma"


async def _market_regime(session, market: str) -> str | None:
    """DSEX vs its 200-day average — the gate the research says the reversal edge depends on."""
    closes = list(
        await session.scalars(
            select(MarketSummary.dsex)
            .where(MarketSummary.market == market, MarketSummary.dsex.isnot(None))
            .order_by(MarketSummary.date.desc())
            .limit(_REGIME_WINDOW)
        )
    )
    if len(closes) < _REGIME_MIN_OBS:
        return None
    return regime_from(closes[0], sum(closes) / len(closes))


def _clean_codes(market: str):
    """Visible, active, non-Z symbols for clean scanner boards."""
    return select(Symbol.code).where(
        Symbol.market == market,
        Symbol.is_active.is_(True),
        Symbol.is_hidden.is_(False),
        Symbol.data_status == "ready",
        or_(Symbol.category.is_(None), Symbol.category != "Z"),
    )


def _adtv_mn(T) -> object:
    return T.avg_volume_20 * T.last_close / 1e6


def _clamp10(value: float) -> int:
    return int(max(0, min(10, round(value))))


def _fmt_pct(value: float | None, suffix: str = "%") -> str:
    if value is None:
        return "n/a"
    return f"{value:+.1f}{suffix}"


def _fmt_x(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}x"


def _extension_note(row: TickerAnalytics) -> str | None:
    near_high = row.pct_from_52w_high is not None and row.pct_from_52w_high >= -3
    hot_rsi = row.rsi_14 is not None and row.rsi_14 >= 72
    strong_run = row.mom_12_1 is not None and row.mom_12_1 >= 35
    far_from_low = row.pct_from_52w_low is not None and row.pct_from_52w_low >= 50
    if near_high and hot_rsi and (strong_run or far_from_low):
        return (
            f"Extended: near 52W high ({row.pct_from_52w_high:+.1f}%), "
            f"RSI {row.rsi_14:.0f}, 12M {row.mom_12_1 or 0:+.0f}%"
        )
    if hot_rsi and strong_run:
        return f"Extended: RSI {row.rsi_14:.0f}, 12M {row.mom_12_1:+.0f}%"
    return None


class ScannerResponse(BaseModel):
    as_of: str | None
    quote_as_of: str | None = None
    tab: str
    # DSEX vs its 200-day average ("above_200dma" | "below_200dma"); None when history is too
    # short to say. The frontend shows a louder caution on reversal boards when below.
    market_regime: str | None = None
    boards: list[ScreenOut]


async def _quality_reversal(session, market: str, limit: int) -> ScreenOut | None:
    """Deep-washout x quality x a 5-day-high break — the backtested flagship (Scheme-3).

    Washed-out (>=40% off the high, still near the low) BUT profitable and reasonably priced, that just
    broke their prior 5-day high. Descriptive; carries a regime caveat (the edge is strongest in a
    recovering market — deepest can be a falling knife in a sustained downtrend)."""
    T = TickerAnalytics
    rows = list(
        await session.scalars(
            select(T)
            .where(
                T.market == market,
                T.code.in_(_clean_codes(market)),
                T.pct_from_52w_high <= _WASHOUT_FROM_HIGH,
                T.pct_from_52w_low <= _NEAR_LOW,
                T.roe > 0,  # profitable
                T.pe_ratio > 0,
                T.pe_ratio <= _MAX_PE,
                _adtv_mn(T) >= _MIN_ADTV_MN,  # liquidity
                T.market_cap_mn >= _MIN_MCAP_MN,
            )
            .order_by(T.pct_from_52w_high.asc(), T.roe.desc())
            .limit(60)  # small candidate set; the 5d-high filter narrows it further
        )
    )
    if not rows:
        return ScreenOut(
            key="quality_reversal",
            title="Quality Reversal",
            description=(
                "Deeply beaten-down but profitable, reasonably-priced names that just broke their "
                "5-day high. Empty is useful too: no clean turn setup today."
            ),
            value_label="% from 52w high",
            group="technical",
            items=[],
        )
    cand = {r.code: r for r in rows}

    # Batch the recent daily bars for the candidates and keep names whose latest close broke the
    # highest high of the prior 5 sessions.
    bars_by_code: dict[str, list[DailyBar]] = {c: [] for c in cand}
    for b in await session.scalars(
        select(DailyBar)
        .where(DailyBar.market == market, DailyBar.code.in_(list(cand)))
        .order_by(DailyBar.code, DailyBar.date.desc())
    ):
        lst = bars_by_code[b.code]
        if len(lst) < _5D + 1:  # newest first: [today, ...prior 5]
            lst.append(b)

    names = {
        s.code: s
        for s in await session.scalars(
            select(Symbol).where(Symbol.market == market, Symbol.code.in_(list(cand)))
        )
    }
    items: list[ScreenItem] = []
    for code, bars in bars_by_code.items():
        if len(bars) < _5D + 1:
            continue
        latest, prior = bars[0], bars[1 : _5D + 1]
        prior_high = max(b.high for b in prior)
        if latest.close <= prior_high:
            continue  # no fresh 5-day-high break
        ta = cand[code]
        s = names.get(code)
        if s and s.category == "Z":
            continue
        adtv_mn = (ta.avg_volume_20 * ta.last_close / 1e6) if ta.avg_volume_20 else None
        # The readable one-liner the sheet leads with: fall + quality + trigger (+ volume when real).
        rel_vol = (latest.volume / ta.avg_volume_20) if ta.avg_volume_20 else None
        why = (
            f"Fell {abs(ta.pct_from_52w_high):.0f}% from its 52-week high, still profitable "
            f"(ROE {ta.roe:.0f}%, P/E {ta.pe_ratio:.0f}), and just broke above its 5-day high"
        )
        why += f" on {rel_vol:.1f}x volume." if rel_vol and rel_vol >= 1.2 else "."
        items.append(
            ScreenItem(
                code=code,
                name=(s.name_en if s else "") or "",
                last_close=ta.last_close,
                value=round(ta.pct_from_52w_high, 1),
                change_1d=None,
                category=s.category if s else None,
                adtv_mn=round(adtv_mn, 2) if adtv_mn else None,
                market_cap_mn=ta.market_cap_mn,
                note=f"ROE {ta.roe:.0f}% · P/E {ta.pe_ratio:.0f}",
                why=why,
            )
        )
    # Deepest washouts first (strongest historical effect), cap to limit.
    items.sort(key=lambda i: i.value)
    return ScreenOut(
        key="quality_reversal",
        title="Quality Reversal",
        description=(
            "Deeply beaten-down but profitable, reasonably-priced names that just broke their 5-day "
            "high. Historically the strongest pattern on DSE — but in a falling market a deep drop can "
            "keep falling. Descriptive, not advice."
        ),
        value_label="% from 52w high",
        group="technical",
        items=items[:limit],
    )


async def _oversold_quality(session, market: str, limit: int) -> ScreenOut:
    """Oversold RSI x profitability — the strongest single signal in our DSE factor study.

    Low RSI positively predicted 60-day returns on 82% of rebalances (IC +0.094) — the zone,
    not a timing trigger. The quality filter (profitable, liquid, non-Z) applies the Scheme-3
    lesson: the washout edge concentrates in real businesses, not junk."""
    T = TickerAnalytics
    rows = list(
        await session.scalars(
            select(T)
            .where(
                T.market == market,
                T.code.in_(_clean_codes(market)),
                T.rsi_14.isnot(None),
                T.rsi_14 <= _OVERSOLD_RSI,
                T.roe > 0,  # profitable — skip the junk washouts
                _adtv_mn(T) >= _MIN_ADTV_MN,
                T.market_cap_mn >= _MIN_MCAP_MN,
            )
            .order_by(T.rsi_14.asc())
            .limit(limit)
        )
    )
    items = [
        ScreenItem(
            code=row.code,
            last_close=row.last_close,
            value=round(row.rsi_14, 0),
            note=f"ROE {_fmt_pct(row.roe)}",
            why=(
                f"RSI at {row.rsi_14:.0f} — deep in the oversold zone that historically led DSE "
                f"recoveries — while the business stays profitable (ROE {row.roe:.0f}%)."
            ),
        )
        for row in rows
    ]
    return ScreenOut(
        key="oversold_quality",
        title="Oversold Quality",
        description=(
            "Profitable, liquid names whose RSI sits in the oversold zone. The strongest single "
            "signal in our DSE study — a zone to research, never a timing call."
        ),
        value_label="RSI",
        group="technical",
        items=items,
    )


async def _trending_board(session, market: str, limit: int) -> ScreenOut:
    """Active Today — the validated EOD self-normalised volume+turnover surge (trending_scores)."""
    T = TickerAnalytics
    investable = select(T.code).where(
        T.market == market,
        T.code.in_(_clean_codes(market)),
        _adtv_mn(T) >= _MIN_ADTV_MN,
        T.market_cap_mn >= _MIN_MCAP_MN,
    )
    rows = list(
        await session.scalars(
            select(TrendingScore)
            .where(TrendingScore.market == market, TrendingScore.code.in_(investable))
            .order_by(TrendingScore.rank)
            .limit(limit)
        )
    )
    codes = [r.code for r in rows]
    names = {
        s.code: s
        for s in await session.scalars(
            select(Symbol).where(Symbol.market == market, Symbol.code.in_(codes))
        )
    }
    quotes = {
        q.code: q
        for q in await session.scalars(
            select(QuoteSnapshot).where(
                QuoteSnapshot.market == market, QuoteSnapshot.code.in_(codes)
            )
        )
    }
    analytics = {
        a.code: a
        for a in await session.scalars(
            select(TickerAnalytics).where(
                TickerAnalytics.market == market, TickerAnalytics.code.in_(codes)
            )
        )
    }
    items = [
        ScreenItem(
            code=r.code,
            name=(names[r.code].name_en if r.code in names else "") or "",
            last_close=(
                quotes[r.code].ltp
                if r.code in quotes
                else analytics[r.code].last_close
                if r.code in analytics
                else 0.0
            ),
            value=round(r.score, 1),
            change_1d=round(r.change_pct, 1),
            category=names[r.code].category if r.code in names else None,
            note="heating_up" if r.heating_up else None,
            why="Unusually active today vs its own normal trading — heating up."
            if r.heating_up
            else "More active than usual today.",
        )
        for r in rows
    ]
    return ScreenOut(
        key="active_today",
        title="Active Today",
        description="Stocks trading unusually heavily versus their own normal — activity, not a call.",
        value_label="activity",
        group="movers",
        items=items,
    )


async def _value_quality(session, market: str, limit: int) -> ScreenOut:
    T = TickerAnalytics
    rows = (
        await session.execute(
            select(T.code, T.last_close, T.pe_vs_sector, T.roe, T.pe_ratio)
            .where(
                T.market == market,
                T.code.in_(_clean_codes(market)),
                T.pe_vs_sector.isnot(None),
                T.pe_vs_sector < 0.8,
                T.pe_ratio > 0,
                T.roe >= 15,
                _adtv_mn(T) >= _MIN_ADTV_MN,
                T.market_cap_mn >= _MIN_MCAP_MN,
            )
            .order_by(T.pe_vs_sector.asc(), T.roe.desc())
            .limit(limit)
        )
    ).all()
    return ScreenOut(
        key="value_quality",
        title="Value + Quality",
        description="Cheaper than sector peers, but still profitable. A value shortlist, not a buy list.",
        value_label="x sector",
        group="value",
        items=[
            ScreenItem(
                code=c,
                last_close=lc,
                value=round(pe_vs, 2),
                note=f"ROE {roe:.0f}% · P/E {pe:.0f}",
                why=f"P/E is {pe_vs:.2f}x of sector median with ROE {roe:.0f}%.",
            )
            for c, lc, pe_vs, roe, pe in rows
            if pe_vs is not None and roe is not None and pe is not None
        ],
    )


async def _dividend_quality(session, market: str, limit: int) -> ScreenOut:
    T = TickerAnalytics
    rows = (
        await session.execute(
            select(T.code, T.last_close, T.dividend_yield, T.roe, T.pe_ratio)
            .where(
                T.market == market,
                T.code.in_(_clean_codes(market)),
                T.dividend_yield.isnot(None),
                T.dividend_yield > 0,
                T.pe_ratio > 0,  # positive EPS; avoids pure yield traps from lossmaking names
                _adtv_mn(T) >= _MIN_ADTV_MN,
                T.market_cap_mn >= _MIN_MCAP_MN,
            )
            .order_by(T.dividend_yield.desc())
            .limit(limit)
        )
    ).all()
    return ScreenOut(
        key="dividend_quality",
        title="Dividend Quality",
        description="Cash-yield names with positive earnings context. Past payout, not a forecast.",
        value_label="yield",
        group="value",
        items=[
            ScreenItem(
                code=c,
                last_close=lc,
                value=round(y, 2),
                note=f"ROE {roe:.0f}%" if roe is not None else "Positive EPS",
                why=f"Trailing cash dividend yield {y:.1f}% with positive EPS.",
            )
            for c, lc, y, roe, _pe in rows
            if y is not None
        ],
    )


def _quality_score(row: TickerAnalytics) -> int:
    # Single source of truth (bulls.analytics) so the board score matches the symbol-page lens card.
    return (
        buffett_quality_score(
            roe=row.roe,
            eps_growth_yoy=row.eps_growth_yoy,
            dividend_yield=row.dividend_yield,
            above_sma_200=row.above_sma_200,
        )
        or 0
    )


async def _lens_buffett_quality(session, market: str, limit: int) -> ScreenOut:
    """Buffett/Munger-style quality screen.

    This is stricter than the one-symbol Investor Lens card: scanner rows must be liquid, profitable,
    high-ROE names, with no obviously weak latest EPS trend when that data is available.
    """
    T = TickerAnalytics
    rows = list(
        await session.scalars(
            select(T)
            .where(
                T.market == market,
                T.code.in_(_clean_codes(market)),
                T.pe_ratio > 0,
                T.roe >= 15,
                or_(T.eps_growth_yoy.is_(None), T.eps_growth_yoy >= 0),
                _adtv_mn(T) >= _MIN_ADTV_MN,
                T.market_cap_mn >= _MIN_MCAP_MN,
            )
            .order_by(T.roe.desc())
            .limit(120)
        )
    )
    items: list[ScreenItem] = []
    for row in rows:
        score = _quality_score(row)
        if score < 7:
            continue
        items.append(
            ScreenItem(
                code=row.code,
                last_close=row.last_close,
                value=float(score),
                note=(
                    f"ROE {_fmt_pct(row.roe)} · EPS {_fmt_pct(row.eps_growth_yoy)} · "
                    f"P/E {_fmt_x(row.pe_ratio)}"
                ),
            )
        )
    items.sort(key=lambda item: (-item.value, item.code))
    return ScreenOut(
        key="lens_buffett_quality",
        title="Quality Lens",
        description=(
            "Buffett/Munger-style screen: strong profitability, positive earnings context and "
            "enough liquidity for research."
        ),
        value_label="score",
        group="value",
        items=items[:limit],
    )


def _graham_score(row: TickerAnalytics) -> int:
    return (
        graham_score(
            pe_ratio=row.pe_ratio,
            pb_ratio=row.pb_ratio,
            pe_vs_sector=row.pe_vs_sector,
            roe=row.roe,
            dividend_yield=row.dividend_yield,
        )
        or 0
    )


async def _lens_graham_value(session, market: str, limit: int) -> ScreenOut:
    T = TickerAnalytics
    rows = list(
        await session.scalars(
            select(T)
            .where(
                T.market == market,
                T.code.in_(_clean_codes(market)),
                T.pe_vs_sector.isnot(None),
                T.pe_vs_sector <= 0.8,
                T.pe_ratio > 0,
                or_(T.pb_ratio.is_(None), T.pb_ratio <= 3),
                T.roe > 0,
                _adtv_mn(T) >= _MIN_ADTV_MN,
                T.market_cap_mn >= _MIN_MCAP_MN,
            )
            .order_by(T.pe_vs_sector.asc())
            .limit(120)
        )
    )
    items: list[ScreenItem] = []
    for row in rows:
        score = _graham_score(row)
        if score < 7:
            continue
        items.append(
            ScreenItem(
                code=row.code,
                last_close=row.last_close,
                value=float(score),
                note=(
                    f"P/E {_fmt_x(row.pe_ratio)} · {_fmt_x(row.pe_vs_sector)} sector · "
                    f"ROE {_fmt_pct(row.roe)}"
                ),
            )
        )
    items.sort(key=lambda item: (-item.value, item.code))
    return ScreenOut(
        key="lens_graham_value",
        title="Graham Value Lens",
        description=(
            "Margin-of-safety screen: cheaper than sector peers, positive earnings and basic "
            "profitability support."
        ),
        value_label="score",
        group="value",
        items=items[:limit],
    )


def _smart_money_score(row: TickerAnalytics) -> int:
    return (
        smart_money_score(
            institute_delta=row.institute_delta, foreign_delta=row.foreign_delta, cmf_20=row.cmf_20
        )
        or 0
    )


def _technical_score(row: TickerAnalytics) -> int | None:
    if (
        row.above_sma_50 is None
        and row.above_sma_200 is None
        and row.mom_12_1 is None
        and row.rsi_14 is None
    ):
        return None
    score = 5.0
    score += 1.5 if row.above_sma_50 is True else -1 if row.above_sma_50 is False else 0
    score += 2 if row.above_sma_200 is True else -2 if row.above_sma_200 is False else 0
    if row.mom_12_1 is not None:
        score += 2 if row.mom_12_1 >= 40 else 1 if row.mom_12_1 > 0 else -1
    if row.rsi_14 is not None:
        score += 1 if 45 <= row.rsi_14 <= 70 else -1 if row.rsi_14 > 80 or row.rsi_14 < 30 else 0
    if row.relative_volume is not None and row.relative_volume >= 1.5:
        score += 1
    if (
        row.pct_from_52w_high is not None
        and row.pct_from_52w_high > -2
        and row.rsi_14
        and row.rsi_14 > 75
    ):
        score -= 1
    if _extension_note(row):
        score = min(score, 6.0)
    return _clamp10(score)


async def _lens_smart_money(session, market: str, limit: int) -> ScreenOut:
    T = TickerAnalytics
    ownership_delta = func.coalesce(T.institute_delta, 0) + func.coalesce(T.foreign_delta, 0)
    rows = list(
        await session.scalars(
            select(T)
            .where(
                T.market == market,
                T.code.in_(_clean_codes(market)),
                ownership_delta >= 1.0,
                _adtv_mn(T) >= _MIN_ADTV_MN,
                T.market_cap_mn >= _MIN_MCAP_MN,
            )
            .order_by(ownership_delta.desc())
            .limit(120)
        )
    )
    items: list[ScreenItem] = []
    for row in rows:
        score = _smart_money_score(row)
        if score < 7:
            continue
        total_delta = (row.institute_delta or 0) + (row.foreign_delta or 0)
        items.append(
            ScreenItem(
                code=row.code,
                last_close=row.last_close,
                value=float(score),
                note=(
                    f"Institutions {_fmt_pct(row.institute_delta, ' pp')} · "
                    f"foreign {_fmt_pct(row.foreign_delta, ' pp')} · total {_fmt_pct(total_delta, ' pp')}"
                ),
            )
        )
    items.sort(key=lambda item: (-item.value, item.code))
    return ScreenOut(
        key="lens_smart_money",
        title="Smart Money Lens",
        description=(
            "Ownership-flow screen: institutions and/or foreign investors increased disclosed stakes, "
            "with liquidity checks."
        ),
        value_label="score",
        group="value",
        items=items[:limit],
    )


def _risk_control_score(row: TickerAnalytics) -> int:
    adtv_mn = (row.avg_volume_20 * row.last_close / 1e6) if row.avg_volume_20 else None
    score = 5.0
    if adtv_mn is not None:
        score += 3 if adtv_mn >= 50 else 2 if adtv_mn >= 20 else 1 if adtv_mn >= 10 else -2
    if row.free_float_cap_mn is not None and row.free_float_cap_mn >= _MIN_FREE_FLOAT_CAP_MN:
        score += 1
    if row.volatility is not None:
        score += 1 if row.volatility <= 35 else -1 if row.volatility >= 60 else 0
    return _clamp10(score)


def _lens_status(score: int | None) -> str:
    if score is None:
        return "No data"
    if score >= 7:
        return "Pass"
    if score >= 4:
        return "Watch"
    return "Weak"


async def _lens_agreement(session, market: str, limit: int) -> ScreenOut:
    """Stocks where several independent lenses line up.

    This is not a strict 5/5 gate. Requiring every style to pass would hide useful candidates: quality
    can be expensive, value can lack momentum, and ownership data can be delayed. The board requires
    broad support plus no major risk-control failure.
    """
    T = TickerAnalytics
    rows = list(
        await session.scalars(
            select(T)
            .where(
                T.market == market,
                T.code.in_(_clean_codes(market)),
                _adtv_mn(T) >= _MIN_ADTV_MN,
                T.market_cap_mn >= _MIN_MCAP_MN,
            )
            .limit(500)
        )
    )
    ranked: list[tuple[int, float, ScreenItem]] = []
    for row in rows:
        scores = {
            "Quality": _quality_score(row),
            "Value": _graham_score(row),
            "Technical": _technical_score(row),
            "Smart Money": _smart_money_score(row),
            "Risk": _risk_control_score(row),
        }
        risk_score = scores["Risk"]
        if risk_score is not None and risk_score < 4:
            continue
        supportive = [name for name, score in scores.items() if score is not None and score >= 7]
        if len(supportive) < 3:
            continue
        available_scores = [score for score in scores.values() if score is not None]
        average_score = sum(available_scores) / len(available_scores) if available_scores else 0.0
        extension = _extension_note(row)
        watch_or_weak = [
            f"{name} {_lens_status(score)}"
            for name, score in scores.items()
            if score is None or score < 7
        ]
        note = f"Pass: {', '.join(supportive)}" + (
            f" · Check: {', '.join(watch_or_weak)}" if watch_or_weak else ""
        )
        if extension:
            note = f"{extension} · {note}"
        ranked.append(
            (
                len(supportive),
                average_score,
                ScreenItem(
                    code=row.code,
                    last_close=row.last_close,
                    value=float(len(supportive)),
                    note=note,
                    why=(
                        f"{len(supportive)}/5 lenses supportive with Risk score "
                        f"{risk_score}/10. {note}"
                    ),
                ),
            )
        )
    ranked.sort(key=lambda row: (-row[0], -row[1], row[2].code))
    return ScreenOut(
        key="lens_agreement",
        title="Multi-Lens Agreement",
        description=(
            "Stocks where at least 3 of 5 lenses are supportive and the risk-control lens is not "
            "caution. A strong research queue, not a recommendation."
        ),
        value_label="lenses",
        group="value",
        items=[item for _count, _avg, item in ranked[:limit]],
    )


async def _lens_risk_control(session, market: str, limit: int) -> ScreenOut:
    T = TickerAnalytics
    rows = list(
        await session.scalars(
            select(T)
            .where(
                T.market == market,
                T.code.in_(_clean_codes(market)),
                _adtv_mn(T) >= 10.0,
                T.market_cap_mn >= _MIN_MCAP_MN,
                or_(T.free_float_cap_mn.is_(None), T.free_float_cap_mn >= _MIN_FREE_FLOAT_CAP_MN),
                or_(T.volatility.is_(None), T.volatility <= 60),
            )
            .order_by((_adtv_mn(T)).desc())
            .limit(120)
        )
    )
    items: list[ScreenItem] = []
    for row in rows:
        score = _risk_control_score(row)
        if score < 7:
            continue
        adtv_mn = (row.avg_volume_20 * row.last_close / 1e6) if row.avg_volume_20 else None
        items.append(
            ScreenItem(
                code=row.code,
                last_close=row.last_close,
                value=float(score),
                note=(
                    f"ADTV ৳{adtv_mn:.1f}mn · volatility {_fmt_pct(row.volatility)}"
                    if adtv_mn is not None
                    else f"Volatility {_fmt_pct(row.volatility)}"
                ),
            )
        )
    items.sort(key=lambda item: (-item.value, item.code))
    return ScreenOut(
        key="lens_risk_control",
        title="Risk-Controlled Lens",
        description=(
            "Taleb-style risk filter: names with better liquidity, free-float support and lower "
            "fragility. This is about tradability, not upside."
        ),
        value_label="score",
        group="value",
        items=items[:limit],
    )


_TABS: dict[str, list[str]] = {
    "today": ["quality_reversal", "oversold_quality", "active_today"],
    "value": ["value_quality", "dividend_quality"],
    "lens": [
        "lens_agreement",
        "lens_buffett_quality",
        "lens_graham_value",
        "lens_smart_money",
        "lens_risk_control",
    ],
}


def _apply_scanner_context(boards: list[ScreenOut]) -> None:
    for board in boards:
        board.evidence = _EVIDENCE.get(board.key)
        if board.key == "oversold_quality":
            board.title = "Oversold Quality"
            board.description = (
                "Profitable, liquid names deep in the oversold zone — the strongest single signal "
                "in our DSE study. A research zone, not a timing call."
            )
        if board.key == "quality_reversal":
            board.title = "Quality Reversal"
            board.description = (
                "Deeply beaten-down but profitable names that just crossed back above their recent "
                "5-day high. A study list, not a buy list — and in a downtrend the deepest can keep falling."
            )
        elif board.key == "active_today":
            board.title = "Active Today"
            board.description = (
                "Clean, liquid names trading unusually heavily versus their own normal pace."
            )
        elif board.key == "most_active":
            board.title = "Top Turnover"
            board.description = "Where money is trading today. Useful for liquidity, not a call."
        elif board.key == "value_quality":
            board.title = "Value + Quality"
            board.description = "Cheaper than sector peers with profitability support."
        elif board.key == "dividend_quality":
            board.title = "Dividend Quality"
            board.description = "Cash-yield names with positive earnings context."
        elif board.key == "lens_agreement":
            board.title = "Multi-Lens Agreement"
            board.description = (
                "At least 3 of 5 lenses are supportive, while risk-control is not caution."
            )
        elif board.key == "lens_buffett_quality":
            board.title = "Quality Lens"
            board.description = (
                "Buffett/Munger-style quality screen: stronger profitability, positive earnings "
                "context and enough liquidity to study."
            )
        elif board.key == "lens_graham_value":
            board.title = "Graham Value Lens"
            board.description = (
                "Margin-of-safety screen: cheaper than sector peers with positive earnings and "
                "basic profitability support."
            )
        elif board.key == "lens_smart_money":
            board.title = "Smart Money Lens"
            board.description = (
                "Tracks disclosed institutional/foreign accumulation with liquidity context."
            )
        elif board.key == "lens_risk_control":
            board.title = "Risk-Controlled Lens"
            board.description = (
                "Filters for better tradability: liquidity, free-float support and lower fragility."
            )
        for item in board.items:
            if board.key == "quality_reversal":
                item.scanner_label = "Broke 5-day high"
                # The builder writes the rich per-name line (fall %, ROE, P/E, volume); only
                # fall back to a generic one if it's somehow missing.
                item.why = item.why or (
                    f"Deep washout: {abs(item.value):.0f}% below 52W high, "
                    f"but profitable and just broke its 5-day high."
                )
                item.how_to_read = (
                    "An observation list, not a buy signal. This pattern's edge is usually strongest in "
                    "a recovering market; in a downtrend the most-fallen names can keep falling. Confirm "
                    "volume, news and whether support holds."
                )
                item.risk_note = (
                    "A deeply fallen stock can keep falling — in a broad downtrend this pattern is often "
                    "a falling knife, not a bottom. This is not a buy signal."
                )
                item.check_next = ["News", "Volume holds", "Support level", "Order size"]
            elif board.key == "oversold_quality":
                item.scanner_label = f"RSI {item.value:.0f}"
                item.how_to_read = (
                    "Oversold marks a zone where selling has historically exhausted on DSE — it "
                    "says nothing about timing. Read why it fell before anything else."
                )
                item.risk_note = (
                    "Oversold can stay oversold, and a genuine business problem deserves a low "
                    "price. This is a research zone, not a buy signal."
                )
                item.check_next = ["Why it fell (news)", "EPS trend", "Support level", "Order size"]
            elif board.key == "active_today":
                item.scanner_label = "Unusual activity"
                item.why = (
                    "Trading activity is above its own normal pace."
                    if item.note != "heating_up"
                    else "Volume and turnover are both unusually strong versus its own normal pace."
                )
                item.how_to_read = (
                    "Start here to see where attention and money are moving today, then check the "
                    "reason before acting."
                )
                item.risk_note = (
                    "Activity can be buying or selling pressure; it does not predict direction."
                )
                item.check_next = ["News", "Price direction", "ADTV/order guide", "Sector move"]
            elif board.key == "most_active":
                item.scanner_label = "High turnover"
                item.why = "Today's traded value is high" + (
                    f" ({item.turnover_mn:.1f} mn Tk)." if item.turnover_mn is not None else "."
                )
                item.how_to_read = (
                    "High turnover helps execution, but still check why the stock is active."
                )
                item.risk_note = (
                    "Turnover alone is not strength; heavy selling can also create turnover."
                )
                item.check_next = ["News", "1D price move", "ADTV/order guide", "Category"]
            elif board.key == "value_quality":
                item.scanner_label = "Value + quality"
                item.why = (
                    f"Cheaper than sector peers ({item.value:.2f}x) with profitability support."
                )
                item.how_to_read = (
                    "Use it as a value shortlist; confirm EPS trend, debt, news and whether price has "
                    "already rerated."
                )
                item.risk_note = "Cheap can be a value trap if earnings are weakening."
                item.check_next = ["EPS trend", "Debt/NAV", "Recent news", "Sector comparison"]
            elif board.key == "dividend_quality":
                item.scanner_label = "Dividend check"
                item.why = f"Trailing cash dividend yield is {item.value:.1f}% with positive earnings context."
                item.how_to_read = (
                    "Useful for income/value study; check record date, payout history and whether EPS "
                    "covers the dividend."
                )
                item.risk_note = "Past dividend does not guarantee future dividend; price adjusts around record date."
                item.check_next = ["Record date", "EPS cover", "Payout history", "Price adjustment"]
            elif board.key == "lens_agreement":
                extended = (item.note or "").startswith("Extended:")
                item.scanner_label = (
                    f"Extended · {item.value:.0f}/5" if extended else f"{item.value:.0f}/5 lenses"
                )
                item.why = f"{item.value:.0f}/5 lenses are supportive. {item.note or ''}".strip()
                item.how_to_read = (
                    "Use this as the first research queue when you want broad agreement instead of "
                    "one isolated signal. Open the stock page to see exactly which lenses pass and "
                    "which ones need confirmation."
                )
                if extended:
                    item.risk_note = (
                        "This stock already looks extended. Do not treat agreement as an entry signal; "
                        "check pullback, support, volume quality and whether the move is already priced in."
                    )
                    item.check_next = ["Pullback/support", "RSI cools", "News", "Order size"]
                else:
                    item.risk_note = (
                        "Multi-lens agreement is still descriptive. It can miss new news, sudden liquidity "
                        "changes, and valuation stretch."
                    )
                    item.check_next = ["Lens comparison", "News", "ADTV/order size", "Key levels"]
            elif board.key == "lens_buffett_quality":
                item.scanner_label = "Quality pass"
                item.why = f"Quality score {item.value:.0f}/10. {item.note or 'Profitability and earnings context support the screen.'}"
                item.how_to_read = (
                    "This is a study list for durable-business candidates. It looks for stronger "
                    "profitability and earnings support, then asks you to verify whether the quality "
                    "is repeatable."
                )
                item.risk_note = (
                    "High quality can still be overpriced or already crowded. Check valuation, debt, "
                    "recent news and whether earnings are one-off."
                )
                item.check_next = ["5Y EPS trend", "Debt/NAV", "Dividend history", "Valuation"]
            elif board.key == "lens_graham_value":
                item.scanner_label = "Value pass"
                item.why = f"Value score {item.value:.0f}/10. {item.note or 'Valuation is cheaper than sector with earnings support.'}"
                item.how_to_read = (
                    "This is a margin-of-safety shortlist. Start here when you want cheaper names, "
                    "then confirm the company is not cheap because the business is deteriorating."
                )
                item.risk_note = (
                    "Cheap can be a value trap. Falling EPS, weak governance, debt or bad news can "
                    "make a low P/E deserve to stay low."
                )
                item.check_next = ["EPS trend", "Debt/NAV", "Latest news", "Sector median"]
            elif board.key == "lens_smart_money":
                item.scanner_label = "Flow pass"
                item.why = f"Ownership-flow score {item.value:.0f}/10. {item.note or 'Disclosed ownership moved in a supportive direction.'}"
                item.how_to_read = (
                    "This shows disclosed institutional/foreign stake changes. Treat it as a clue "
                    "about participation, not proof that price must rise."
                )
                item.risk_note = (
                    "Disclosure is delayed and can be noisy. Institutions can also buy early, sell "
                    "later, or be wrong."
                )
                item.check_next = ["Disclosure date", "CMF/OBV", "Price reaction", "Volume quality"]
            elif board.key == "lens_risk_control":
                item.scanner_label = "Tradable"
                item.why = f"Risk-control score {item.value:.0f}/10. {item.note or 'Liquidity and fragility filters look cleaner.'}"
                item.how_to_read = (
                    "Use this to find names where entry and exit may be less painful. It does not say "
                    "the stock is cheap or ready to move."
                )
                item.risk_note = (
                    "Even liquid stocks can gap, hit circuit limits, or move against you. Keep order "
                    "size and stop discipline separate from the screen."
                )
                item.check_next = [
                    "ADTV/order size",
                    "Bid-ask spread",
                    "Volatility",
                    "Support level",
                ]


@router.get("/scanner/radar")
async def radar(
    tenant: CurrentTenant,
    session: DbSession,
    viewer: OptionalUser,
    tab: str = Query("today"),
    watched: bool = Query(False),
    limit: int = Query(10, ge=1, le=25),
) -> ScannerResponse:
    enforce_market_feature(tenant, "curated_screens")
    market = tenant.market
    keys = _TABS.get(tab, _TABS["today"])

    boards: list[ScreenOut] = []
    for key in keys:
        if key == "quality_reversal":
            b = await _quality_reversal(session, market, limit)
        elif key == "oversold_quality":
            b = await _oversold_quality(session, market, limit)
        elif key == "active_today":
            b = await _trending_board(session, market, limit)
        elif key == "value_quality":
            b = await _value_quality(session, market, limit)
        elif key == "dividend_quality":
            b = await _dividend_quality(session, market, limit)
        elif key == "lens_agreement":
            b = await _lens_agreement(session, market, limit)
        elif key == "lens_buffett_quality":
            b = await _lens_buffett_quality(session, market, limit)
        elif key == "lens_graham_value":
            b = await _lens_graham_value(session, market, limit)
        elif key == "lens_smart_money":
            b = await _lens_smart_money(session, market, limit)
        elif key == "lens_risk_control":
            b = await _lens_risk_control(session, market, limit)
        else:
            continue
        boards.append(b)

    await _enrich(session, market, boards)

    if watched and viewer is not None:
        watched_codes = set(
            await session.scalars(
                select(WatchlistItem.code).where(
                    WatchlistItem.user_id == viewer.id, WatchlistItem.market == market
                )
            )
        )
        for b in boards:
            b.items = [i for i in b.items if i.code in watched_codes]

    _apply_scanner_context(boards)
    if watched:
        boards = [b for b in boards if b.items]

    as_of = await session.scalar(
        select(func.max(TickerAnalytics.as_of_date)).where(TickerAnalytics.market == market)
    )
    quote_ts = await session.scalar(
        select(func.max(QuoteSnapshot.as_of)).where(QuoteSnapshot.market == market)
    )
    # Live regime gate (spec §2): only fetched when a regime-sensitive board is on this tab.
    regime = None
    if any(b.key in _REGIME_SENSITIVE for b in boards):
        regime = await _market_regime(session, market)

    return ScannerResponse(
        as_of=str(as_of) if as_of else None,
        quote_as_of=quote_ts.isoformat() if quote_ts else None,
        tab=tab,
        market_regime=regime,
        boards=boards,
    )
