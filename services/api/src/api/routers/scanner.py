"""Scanner — the "hunt with the data" surface that replaces the passive Watchlist tab.

Two retail-facing tabs, assembled from boards:
- **Today** — Quality Reversal (the research flagship), Active Today (validated EOD trending), and
  Top Turnover.
- **Value** — Value + Quality and Dividend.

Most boards reuse the Market screener's `build_screen` / the persisted `trending_scores`; the only
new logic here is **Quality Reversal** (docs/specs/scanner.md §0.1) — deep-washout x quality x a
5-day-high break, the backtested winner (Scheme-3). `?watched=true` scopes every board to the
caller's watchlist. Descriptive, liquidity-gated, freshness-stamped — never advice.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from api.deps import CurrentTenant, DbSession, OptionalUser, visible_codes
from api.routers.screener import ScreenItem, ScreenOut, build_screen
from bulls.core.models import (
    DailyBar,
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

# Quality Reversal thresholds (from dse-trading-research.md Scheme-3).
_WASHOUT_FROM_HIGH = -40.0  # >=40% off the 52-week high
_NEAR_LOW = 15.0  # still within 15% of the 52-week low
_MAX_PE = 25.0  # reasonably priced
_5D = 5  # prior-day window for the breakout trigger


class ScannerResponse(BaseModel):
    as_of: str | None
    quote_as_of: str | None = None
    tab: str
    boards: list[ScreenOut]


async def _quality_reversal(session, market: str, limit: int) -> ScreenOut | None:
    """Deep-washout x quality x a 5-day-high break — the backtested flagship (Scheme-3).

    Washed-out (>=40% off the high, still near the low) BUT profitable and reasonably priced, that just
    broke their prior 5-day high. Descriptive; carries a regime caveat (the edge is strongest in a
    recovering market — deepest can be a falling knife in a sustained downtrend)."""
    codes = visible_codes(market)
    T = TickerAnalytics
    rows = list(
        await session.scalars(
            select(T)
            .where(
                T.market == market,
                T.code.in_(codes),
                T.pct_from_52w_high <= _WASHOUT_FROM_HIGH,
                T.pct_from_52w_low <= _NEAR_LOW,
                T.roe > 0,  # profitable
                T.pe_ratio > 0,
                T.pe_ratio <= _MAX_PE,
                (T.avg_volume_20 * T.last_close / 1e6) >= _MIN_ADTV_MN,  # liquidity
                T.market_cap_mn >= _MIN_MCAP_MN,
            )
            .limit(60)  # small candidate set; the 5d-high filter narrows it further
        )
    )
    if not rows:
        return ScreenOut(
            key="quality_reversal", title="", description="", value_label="", group="technical",
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
        adtv_mn = (ta.avg_volume_20 * ta.last_close / 1e6) if ta.avg_volume_20 else None
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
                why=(
                    f"{ta.pct_from_52w_high:.0f}% off its 52-week high yet profitable "
                    f"(ROE {ta.roe:.0f}%, P/E {ta.pe_ratio:.0f}) — just broke its 5-day high."
                ),
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


async def _trending_board(session, market: str, limit: int) -> ScreenOut:
    """Active Today — the validated EOD self-normalised volume+turnover surge (trending_scores)."""
    rows = list(
        await session.scalars(
            select(TrendingScore)
            .where(TrendingScore.market == market)
            .order_by(TrendingScore.rank)
            .limit(limit)
        )
    )
    names = {
        s.code: s
        for s in await session.scalars(
            select(Symbol).where(Symbol.market == market, Symbol.code.in_([r.code for r in rows]))
        )
    }
    items = [
        ScreenItem(
            code=r.code,
            name=(names[r.code].name_en if r.code in names else "") or "",
            last_close=0.0,
            value=round(r.change_pct, 1),
            change_1d=round(r.change_pct, 1),
            category=names[r.code].category if r.code in names else None,
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
        value_label="% today",
        group="movers",
        items=items,
    )


_TABS: dict[str, list[str]] = {
    "today": ["quality_reversal", "active_today", "most_active"],
    "value": ["value_vs_sector", "dividend_yield"],
}


@router.get("/scanner/radar")
async def radar(
    tenant: CurrentTenant,
    session: DbSession,
    viewer: OptionalUser,
    tab: str = Query("today"),
    watched: bool = Query(False),
    limit: int = Query(10, ge=1, le=25),
) -> ScannerResponse:
    market = tenant.market
    keys = _TABS.get(tab, _TABS["today"])

    boards: list[ScreenOut] = []
    for key in keys:
        if key == "quality_reversal":
            b = await _quality_reversal(session, market, limit)
        elif key == "active_today":
            b = await _trending_board(session, market, limit)
        else:
            b = await build_screen(session, market, key, limit, tenant_id=tenant.name)
        if b is not None:
            boards.append(b)

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

    boards = [b for b in boards if b.items]  # hide empty boards

    as_of = await session.scalar(select(func.max(TickerAnalytics.as_of_date)).where(TickerAnalytics.market == market))
    quote_ts = await session.scalar(
        select(func.max(QuoteSnapshot.as_of)).where(QuoteSnapshot.market == market)
    )
    return ScannerResponse(
        as_of=str(as_of) if as_of else None,
        quote_as_of=quote_ts.isoformat() if quote_ts else None,
        tab=tab,
        boards=boards,
    )
