from __future__ import annotations

import datetime as dt
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.institutional_research.options import (
    MAX_DISPLAY_CONTRACTS_PER_SIDE,
    _cache_key,
    option_chain_preview_out,
)
from api.routers.institutional_research import _require_options_preview_access
from bulls.market_data.options import (
    OptionChainSnapshot,
    OptionContract,
    analyze_option_chain,
)


def _contract(option_type: str, strike: float) -> OptionContract:
    return OptionContract(
        contract_symbol=f"TEST-{option_type}-{strike}",
        option_type=option_type,  # type: ignore[arg-type]
        expiration=dt.date(2026, 8, 21),
        strike=strike,
        currency="USD",
        last_price=2.5,
        bid=2.4,
        ask=2.6,
        midpoint=2.5,
        spread_pct=8.0,
        volume=100,
        open_interest=200,
        implied_volatility_pct=55.0,
        in_the_money=False,
        liquidity="usable",
    )


def test_preview_is_bounded_and_retains_full_chain_metrics() -> None:
    contracts = [
        _contract(option_type, float(strike))
        for option_type in ("call", "put")
        for strike in range(25, 126)
    ]
    snapshot = OptionChainSnapshot(
        code="TEST",
        expiration=dt.date(2026, 8, 21),
        available_expirations=[dt.date(2026, 8, 21)],
        underlying_price=75.0,
        underlying_as_of=dt.datetime(2026, 7, 17, 20, tzinfo=dt.UTC),
        market_state="CLOSED",
        fetched_at=dt.datetime(2026, 7, 17, 20, 2, tzinfo=dt.UTC),
        currency="USD",
        source="yahoo_unofficial",
        source_url="https://finance.yahoo.com/quote/TEST/options",
        contracts=contracts,
    )
    workspace_id = uuid.uuid4()

    output = option_chain_preview_out(
        analyze_option_chain(snapshot),
        tenant_id="bullsofwallst",
        workspace_id=workspace_id,
    )

    assert output.tenant_id == "bullsofwallst"
    assert output.workspace_id == workspace_id
    assert output.metrics.contract_count == 202
    assert output.metrics.displayed_contract_count == MAX_DISPLAY_CONTRACTS_PER_SIDE * 2
    assert len(output.contracts) == MAX_DISPLAY_CONTRACTS_PER_SIDE * 2
    assert min(contract.strike for contract in output.contracts) >= 55
    assert max(contract.strike for contract in output.contracts) <= 94
    assert output.experimental is True
    assert output.access_scope == "platform_admin"
    assert "do not identify trade direction" in output.summary


def test_cache_identity_cannot_cross_tenants_or_expirations() -> None:
    workspace = uuid.uuid4()
    other_workspace = uuid.uuid4()
    dse = _cache_key(
        tenant_id="bullsofdhaka",
        workspace_id=workspace,
        code="TEST",
        expiration=None,
    )
    us = _cache_key(
        tenant_id="bullsofwallst",
        workspace_id=workspace,
        code="TEST",
        expiration=None,
    )
    dated = _cache_key(
        tenant_id="bullsofwallst",
        workspace_id=workspace,
        code="TEST",
        expiration=dt.date(2026, 8, 21),
    )
    other = _cache_key(
        tenant_id="bullsofwallst",
        workspace_id=other_workspace,
        code="TEST",
        expiration=None,
    )

    assert dse != us
    assert us != dated
    assert us != other
    assert ":US:TEST:" in us


def test_options_preview_rejects_dse_before_role_check() -> None:
    with pytest.raises(HTTPException) as caught:
        _require_options_preview_access(
            SimpleNamespace(market="DSE"),
            SimpleNamespace(role="user"),
        )

    assert caught.value.status_code == 404


def test_options_preview_rejects_non_admin_us_user() -> None:
    with pytest.raises(HTTPException) as caught:
        _require_options_preview_access(
            SimpleNamespace(market="US"),
            SimpleNamespace(role="user"),
        )

    assert caught.value.status_code == 403


def test_options_preview_accepts_us_admin() -> None:
    _require_options_preview_access(
        SimpleNamespace(market="US"),
        SimpleNamespace(role="admin"),
    )
