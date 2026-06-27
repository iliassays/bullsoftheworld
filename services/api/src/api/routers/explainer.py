"""AI technicals explainer — "explain these levels in plain language".

Computes the technical facts with the deterministic analytics engine, lets the LLM only narrate
them educationally, runs the result through the no-advice gate, and caches in Redis (the model
call is expensive; the same snapshot shouldn't re-run it).
"""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from api.deps import CurrentTenant, DbSession
from api.i18n import language_for
from bulls.ai.tasks.explainer import TechnicalsFacts, explain_technicals
from bulls.analytics import compute
from bulls.core.config import get_settings
from bulls.core.models import DailyBar, Symbol

router = APIRouter(tags=["explainer"])

CACHE_TTL = 86400  # technicals change once a day (EOD); the key includes as_of_date, so a 24h
# TTL means each ticker is generated at most once per data update and then served from cache to
# everyone — keeps the per-ticker LLM cost flat regardless of how many users view it.
_LOOKBACK = 260


class ExplainerResponse(BaseModel):
    code: str
    explanation: str
    as_of_date: str


@router.get("/symbols/{code}/explainer")
async def get_explainer(code: str, tenant: CurrentTenant, session: DbSession) -> ExplainerResponse:
    code = code.upper()
    symbol = await session.get(Symbol, (tenant.market, code))
    if symbol is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")

    bars = list(
        await session.scalars(
            select(DailyBar)
            .where(DailyBar.market == tenant.market, DailyBar.code == code)
            .order_by(DailyBar.date.desc())
            .limit(_LOOKBACK)
        )
    )
    if not bars:
        raise HTTPException(status_code=404, detail=f"No price history for {code!r} yet")
    ta = compute(list(reversed(bars)))

    cache_key = f"explainer:{tenant.market}:{code}:{tenant.locale}:{ta.as_of_date}"
    redis = aioredis.from_url(get_settings().redis_url)
    try:
        cached = await redis.get(cache_key)
        if cached:
            return ExplainerResponse.model_validate_json(cached)

        facts = TechnicalsFacts(
            code=code,
            name=symbol.name_en,
            as_of_date=str(ta.as_of_date),
            last_close=ta.last_close,
            above_sma_50=ta.above_sma_50,
            above_sma_200=ta.above_sma_200,
            rsi_14=ta.rsi_14,
            nearest_support=ta.nearest_support,
            nearest_resistance=ta.nearest_resistance,
            week52_high=ta.week52_high,
            week52_low=ta.week52_low,
            pct_from_52w_high=ta.pct_from_52w_high,
            relative_volume=ta.relative_volume,
        )
        explanation = await explain_technicals(facts, language=language_for(tenant.locale))
        resp = ExplainerResponse(code=code, explanation=explanation, as_of_date=str(ta.as_of_date))
        await redis.set(cache_key, resp.model_dump_json(), ex=CACHE_TTL)
        return resp
    finally:
        await redis.aclose()
