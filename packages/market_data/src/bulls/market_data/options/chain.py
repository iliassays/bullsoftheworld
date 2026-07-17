"""Provider-neutral option-chain values and deterministic descriptive analytics.

This module deliberately does not make a directional prediction.  It turns one observed chain
into bounded, auditable measurements that can be compared with later observations or supplied to
an optional reasoning layer as evidence.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections.abc import Iterable
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

OptionType = Literal["call", "put"]
OptionLiquidity = Literal["usable", "thin", "unquoted"]
ChainQuality = Literal["usable", "thin", "no_liquid_options"]


class OptionContract(BaseModel):
    contract_symbol: str
    option_type: OptionType
    expiration: dt.date
    strike: float = Field(gt=0)
    currency: str
    last_price: float | None = None
    bid: float | None = None
    ask: float | None = None
    midpoint: float | None = None
    spread_pct: float | None = None
    volume: int | None = Field(default=None, ge=0)
    open_interest: int | None = Field(default=None, ge=0)
    implied_volatility_pct: float | None = Field(default=None, ge=0)
    in_the_money: bool
    last_trade_at: dt.datetime | None = None
    contract_size: str | None = None
    liquidity: OptionLiquidity


class OptionChainSnapshot(BaseModel):
    market: Literal["US"] = "US"
    code: str
    expiration: dt.date
    available_expirations: list[dt.date]
    underlying_price: float = Field(gt=0)
    underlying_as_of: dt.datetime | None
    market_state: str | None
    fetched_at: dt.datetime
    currency: str
    source: str
    source_url: str
    is_delayed: bool = True
    contracts: list[OptionContract]


class OptionChainMetrics(BaseModel):
    quality: ChainQuality
    contract_count: int = Field(ge=0)
    liquid_contract_count: int = Field(ge=0)
    two_sided_quote_pct: float = Field(ge=0, le=100)
    call_volume: int = Field(ge=0)
    put_volume: int = Field(ge=0)
    put_call_volume_ratio: float | None = Field(default=None, ge=0)
    call_open_interest: int = Field(ge=0)
    put_open_interest: int = Field(ge=0)
    put_call_open_interest_ratio: float | None = Field(default=None, ge=0)
    atm_implied_volatility_pct: float | None = Field(default=None, ge=0)
    approximate_downside_skew_pp: float | None = None
    implied_move_pct: float | None = Field(default=None, ge=0)


class OptionChainAnalysis(BaseModel):
    snapshot: OptionChainSnapshot
    metrics: OptionChainMetrics


@runtime_checkable
class OptionChainProvider(Protocol):
    market: Literal["US"]

    async def get_option_chain(
        self,
        code: str,
        expiration: dt.date | None = None,
    ) -> OptionChainSnapshot: ...


def _total(contracts: Iterable[OptionContract], field: Literal["volume", "open_interest"]) -> int:
    return sum(getattr(contract, field) or 0 for contract in contracts)


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 3) if denominator > 0 else None


def _median(values: Iterable[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return round(statistics.median(clean), 2) if clean else None


def _implied_move_pct(snapshot: OptionChainSnapshot) -> float | None:
    """Approximate one-expiry move using the nearest same-strike call and put midpoints."""

    calls = {
        contract.strike: contract
        for contract in snapshot.contracts
        if contract.option_type == "call" and contract.midpoint is not None
    }
    puts = {
        contract.strike: contract
        for contract in snapshot.contracts
        if contract.option_type == "put" and contract.midpoint is not None
    }
    paired = calls.keys() & puts.keys()
    if not paired:
        return None
    strike = min(paired, key=lambda value: abs(value - snapshot.underlying_price))
    call_mid = calls[strike].midpoint
    put_mid = puts[strike].midpoint
    if call_mid is None or put_mid is None:
        return None
    return round((call_mid + put_mid) / snapshot.underlying_price * 100, 2)


def analyze_option_chain(snapshot: OptionChainSnapshot) -> OptionChainAnalysis:
    """Calculate descriptive chain measures without inventing Greeks or trading direction."""

    contracts = snapshot.contracts
    calls = [contract for contract in contracts if contract.option_type == "call"]
    puts = [contract for contract in contracts if contract.option_type == "put"]
    two_sided = [contract for contract in contracts if contract.midpoint is not None]
    liquid = [contract for contract in contracts if contract.liquidity == "usable"]

    call_volume = _total(calls, "volume")
    put_volume = _total(puts, "volume")
    call_oi = _total(calls, "open_interest")
    put_oi = _total(puts, "open_interest")
    quote_coverage = round(len(two_sided) / len(contracts) * 100, 1) if contracts else 0.0

    if not liquid:
        quality: ChainQuality = "no_liquid_options"
    elif len(liquid) < max(4, round(len(contracts) * 0.1)) or quote_coverage < 25:
        quality = "thin"
    else:
        quality = "usable"

    spot = snapshot.underlying_price
    iv_candidates = [
        contract.implied_volatility_pct
        for contract in contracts
        if contract.liquidity != "unquoted" and abs(contract.strike / spot - 1) <= 0.05
    ]
    downside_put_iv = _median(
        contract.implied_volatility_pct
        for contract in puts
        if contract.liquidity != "unquoted" and 0.90 <= contract.strike / spot <= 0.98
    )
    upside_call_iv = _median(
        contract.implied_volatility_pct
        for contract in calls
        if contract.liquidity != "unquoted" and 1.02 <= contract.strike / spot <= 1.10
    )
    skew = (
        round(downside_put_iv - upside_call_iv, 2)
        if downside_put_iv is not None and upside_call_iv is not None
        else None
    )

    return OptionChainAnalysis(
        snapshot=snapshot,
        metrics=OptionChainMetrics(
            quality=quality,
            contract_count=len(contracts),
            liquid_contract_count=len(liquid),
            two_sided_quote_pct=quote_coverage,
            call_volume=call_volume,
            put_volume=put_volume,
            put_call_volume_ratio=_ratio(put_volume, call_volume),
            call_open_interest=call_oi,
            put_open_interest=put_oi,
            put_call_open_interest_ratio=_ratio(put_oi, call_oi),
            atm_implied_volatility_pct=_median(iv_candidates),
            approximate_downside_skew_pp=skew,
            implied_move_pct=_implied_move_pct(snapshot),
        ),
    )
