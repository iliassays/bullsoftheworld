"""Owner-preview option-chain read model for Atlas.

The read is intentionally isolated from the company dossier.  An unavailable experimental source
must never make the core research record unavailable.  Redis is an optimization only; cache
failure is fail-open and provider failures remain explicit.
"""

from __future__ import annotations

import datetime as dt
import uuid
from contextlib import suppress
from typing import Literal

import redis.asyncio as aioredis
from pydantic import Field
from redis.exceptions import RedisError

from api.institutional_research.schemas import ApiModel
from bulls.core.config import get_settings
from bulls.market_data.options import OptionChainAnalysis, analyze_option_chain
from bulls.market_data.providers.us_yahoo_options import YahooUsOptionChainProvider

OPTIONS_CACHE_TTL_SECONDS = 900
MAX_DISPLAY_CONTRACTS_PER_SIDE = 40


class OptionContractOut(ApiModel):
    contract_symbol: str
    option_type: Literal["call", "put"]
    expiration: dt.date
    strike: float
    currency: str
    last_price: float | None
    bid: float | None
    ask: float | None
    midpoint: float | None
    spread_pct: float | None
    volume: int | None
    open_interest: int | None
    implied_volatility_pct: float | None
    in_the_money: bool
    last_trade_at: dt.datetime | None
    liquidity: Literal["usable", "thin", "unquoted"]


class OptionMetricsOut(ApiModel):
    quality: Literal["usable", "thin", "no_liquid_options"]
    contract_count: int
    displayed_contract_count: int
    liquid_contract_count: int
    two_sided_quote_pct: float = Field(ge=0, le=100)
    call_volume: int
    put_volume: int
    put_call_volume_ratio: float | None
    call_open_interest: int
    put_open_interest: int
    put_call_open_interest_ratio: float | None
    atm_implied_volatility_pct: float | None
    approximate_downside_skew_pp: float | None
    implied_move_pct: float | None


class OptionChainPreviewOut(ApiModel):
    tenant_id: str
    market: Literal["US"] = "US"
    workspace_id: uuid.UUID
    code: str
    expiration: dt.date
    available_expirations: list[dt.date]
    underlying_price: float
    underlying_as_of: dt.datetime | None
    market_state: str | None
    fetched_at: dt.datetime
    currency: str
    provider: str
    source_url: str
    is_delayed: bool
    experimental: bool = True
    access_scope: Literal["platform_admin"] = "platform_admin"
    summary: str
    metrics: OptionMetricsOut
    contracts: list[OptionContractOut]
    limitations: list[str]


def _display_contracts(analysis: OptionChainAnalysis):
    spot = analysis.snapshot.underlying_price
    selected = []
    for option_type in ("call", "put"):
        side = [
            contract
            for contract in analysis.snapshot.contracts
            if contract.option_type == option_type
        ]
        nearest = sorted(side, key=lambda contract: abs(contract.strike - spot))[
            :MAX_DISPLAY_CONTRACTS_PER_SIDE
        ]
        selected.extend(nearest)
    return sorted(selected, key=lambda contract: (contract.strike, contract.option_type))


def _summary(analysis: OptionChainAnalysis) -> str:
    metrics = analysis.metrics
    if metrics.quality == "no_liquid_options":
        return (
            "No contracts passed the bounded liquidity check. Treat the chain as an explicit "
            "absence state, not as evidence of neutral positioning."
        )
    quality = "Usable" if metrics.quality == "usable" else "Thin"
    oi = (
        f" Put/call open-interest ratio is {metrics.put_call_open_interest_ratio:.2f}."
        if metrics.put_call_open_interest_ratio is not None
        else " Put/call open-interest ratio is unavailable."
    )
    return (
        f"{quality} two-sided quotes cover {metrics.two_sided_quote_pct:.1f}% of returned "
        f"contracts.{oi} These measurements describe the observed chain; they do not identify "
        "trade direction or predict return."
    )


def option_chain_preview_out(
    analysis: OptionChainAnalysis,
    *,
    tenant_id: str,
    workspace_id: uuid.UUID,
) -> OptionChainPreviewOut:
    displayed = _display_contracts(analysis)
    snapshot = analysis.snapshot
    metrics = analysis.metrics
    return OptionChainPreviewOut(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        code=snapshot.code,
        expiration=snapshot.expiration,
        available_expirations=snapshot.available_expirations,
        underlying_price=snapshot.underlying_price,
        underlying_as_of=snapshot.underlying_as_of,
        market_state=snapshot.market_state,
        fetched_at=snapshot.fetched_at,
        currency=snapshot.currency,
        provider=snapshot.source,
        source_url=snapshot.source_url,
        is_delayed=snapshot.is_delayed,
        summary=_summary(analysis),
        metrics=OptionMetricsOut(
            **metrics.model_dump(),
            displayed_contract_count=len(displayed),
        ),
        contracts=[OptionContractOut.model_validate(item.model_dump()) for item in displayed],
        limitations=[
            "Experimental owner preview from an unofficial, unlicensed source; not approved for public redistribution.",
            "Quotes may be delayed, stale, incomplete, or absent. Atlas does not infer missing values.",
            "Volume and open interest do not reveal whether a contract was bought or sold, opened or closed.",
            "Greeks and historical volatility surfaces are unavailable in this preview and are not estimated.",
        ],
    )


def _cache_key(
    *,
    tenant_id: str,
    workspace_id: uuid.UUID,
    code: str,
    expiration: dt.date | None,
) -> str:
    expiry = expiration.isoformat() if expiration is not None else "nearest"
    return f"atlas:options:v1:{tenant_id}:{workspace_id}:US:{code}:{expiry}"


async def load_option_chain_preview(
    *,
    tenant_id: str,
    workspace_id: uuid.UUID,
    code: str,
    expiration: dt.date | None,
) -> OptionChainPreviewOut:
    key = _cache_key(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        code=code,
        expiration=expiration,
    )
    redis = aioredis.from_url(get_settings().redis_url)
    try:
        try:
            cached = await redis.get(key)
        except RedisError:
            cached = None
        if cached:
            return OptionChainPreviewOut.model_validate_json(cached)

        snapshot = await YahooUsOptionChainProvider().get_option_chain(code, expiration)
        response = option_chain_preview_out(
            analyze_option_chain(snapshot),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        with suppress(RedisError):
            await redis.set(key, response.model_dump_json(by_alias=True), ex=OPTIONS_CACHE_TTL_SECONDS)
        return response
    finally:
        with suppress(RedisError):
            await redis.aclose()
