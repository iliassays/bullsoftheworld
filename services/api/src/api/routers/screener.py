"""Discovery screener — top tickers per descriptive condition, as fast SQL over ticker_analytics.

Every screen is a computed FACT (RSI <= 30, close near support, positive money flow, ...), named by
the condition, never by implication. No advice, no AI — pure data the analytics scheduler persisted.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import ColumnElement, and_, select

from api.deps import CurrentTenant, DbSession, visible_codes
from bulls.core.models import QuoteSnapshot, TickerAnalytics

router = APIRouter(tags=["screener"])

T = TickerAnalytics
PER_SCREEN = 8

# Reused metric expressions
_PCT_ABOVE_SUPPORT = (T.last_close - T.nearest_support) / T.nearest_support * 100
_PCT_BELOW_RESISTANCE = (T.nearest_resistance - T.last_close) / T.last_close * 100
_PCT_ABOVE_200 = (T.last_close - T.sma_200) / T.sma_200 * 100


@dataclass
class ScreenSpec:
    key: str
    title: str
    description: str
    value_label: str
    where: ColumnElement[bool]
    order: ColumnElement
    value: ColumnElement


# Order here is the display order on the dashboard (structure → momentum → volume → trend → range).
_SCREENS: list[ScreenSpec] = [
    ScreenSpec(
        "near_support",
        "Near support",
        "Trading just above a support level",
        "% above support",
        and_(
            T.nearest_support.isnot(None),
            T.last_close >= T.nearest_support,
            T.last_close <= T.nearest_support * 1.03,
        ),
        _PCT_ABOVE_SUPPORT.asc(),
        _PCT_ABOVE_SUPPORT,
    ),
    ScreenSpec(
        "near_resistance",
        "Near resistance",
        "Approaching a resistance level",
        "% below resistance",
        and_(
            T.nearest_resistance.isnot(None),
            T.last_close <= T.nearest_resistance,
            T.last_close >= T.nearest_resistance * 0.97,
        ),
        _PCT_BELOW_RESISTANCE.asc(),
        _PCT_BELOW_RESISTANCE,
    ),
    ScreenSpec(
        "oversold",
        "Oversold (RSI ≤ 30)",
        "Low RSI — historically an oversold zone",
        "RSI",
        T.rsi_14 <= 30,
        T.rsi_14.asc(),
        T.rsi_14,
    ),
    ScreenSpec(
        "overbought",
        "Overbought (RSI ≥ 70)",
        "High RSI — historically an overbought zone",
        "RSI",
        T.rsi_14 >= 70,
        T.rsi_14.desc(),
        T.rsi_14,
    ),
    ScreenSpec(
        "accumulation",
        "Accumulation",
        "Volume flowing in (positive money flow)",
        "CMF",
        T.cmf_20 > 0,
        T.cmf_20.desc(),
        T.cmf_20,
    ),
    ScreenSpec(
        "distribution",
        "Distribution",
        "Volume flowing out (negative money flow)",
        "CMF",
        T.cmf_20 < 0,
        T.cmf_20.asc(),
        T.cmf_20,
    ),
    ScreenSpec(
        "unusual_volume",
        "Unusual volume",
        "Trading well above its 20-day average",
        "x avg vol",
        T.relative_volume >= 1.5,
        T.relative_volume.desc(),
        T.relative_volume,
    ),
    ScreenSpec(
        "uptrend",
        "Above 200-day average",
        "In a longer-term uptrend",
        "% above 200-DMA",
        and_(T.above_sma_200.is_(True), T.sma_200.isnot(None)),
        _PCT_ABOVE_200.desc(),
        _PCT_ABOVE_200,
    ),
    ScreenSpec(
        "near_52w_high",
        "Near 52-week high",
        "Within 5% of the yearly high",
        "% from high",
        T.pct_from_52w_high >= -5,
        T.pct_from_52w_high.desc(),
        T.pct_from_52w_high,
    ),
    ScreenSpec(
        "near_52w_low",
        "Near 52-week low",
        "Within 5% of the yearly low",
        "% from low",
        and_(T.pct_from_52w_low.isnot(None), T.pct_from_52w_low <= 5),
        T.pct_from_52w_low.asc(),
        T.pct_from_52w_low,
    ),
]


class ScreenItem(BaseModel):
    code: str
    last_close: float
    value: float


class ScreenOut(BaseModel):
    key: str
    title: str
    description: str
    value_label: str
    items: list[ScreenItem]


class ScreensResponse(BaseModel):
    as_of: str | None
    screens: list[ScreenOut]


async def _movers(session, market: str, *, gainers: bool) -> ScreenOut:
    order = QuoteSnapshot.change_pct.desc() if gainers else QuoteSnapshot.change_pct.asc()
    rows = (
        await session.execute(
            select(QuoteSnapshot.code, QuoteSnapshot.ltp, QuoteSnapshot.change_pct)
            .where(
                QuoteSnapshot.market == market,
                QuoteSnapshot.code.in_(visible_codes(market)),
            )
            .order_by(order)
            .limit(PER_SCREEN)
        )
    ).all()
    return ScreenOut(
        key="top_gainers" if gainers else "top_losers",
        title="Top gainers" if gainers else "Top losers",
        description="Biggest moves up today" if gainers else "Biggest moves down today",
        value_label="% today",
        items=[ScreenItem(code=c, last_close=p, value=round(chg, 2)) for c, p, chg in rows],
    )


@router.get("/screens")
async def screens(tenant: CurrentTenant, session: DbSession) -> ScreensResponse:
    out: list[ScreenOut] = []
    for spec in _SCREENS:
        rows = (
            await session.execute(
                select(T.code, T.last_close, spec.value)
                .where(
                    T.market == tenant.market,
                    spec.where,
                    T.code.in_(visible_codes(tenant.market)),
                )
                .order_by(spec.order)
                .limit(PER_SCREEN)
            )
        ).all()
        out.append(
            ScreenOut(
                key=spec.key,
                title=spec.title,
                description=spec.description,
                value_label=spec.value_label,
                items=[
                    ScreenItem(code=c, last_close=lc, value=round(v, 2))
                    for c, lc, v in rows
                    if v is not None
                ],
            )
        )

    out.append(await _movers(session, tenant.market, gainers=True))
    out.append(await _movers(session, tenant.market, gainers=False))

    as_of = await session.scalar(select(T.as_of_date).where(T.market == tenant.market).limit(1))
    return ScreensResponse(as_of=str(as_of) if as_of else None, screens=out)
