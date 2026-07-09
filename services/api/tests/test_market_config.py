"""Public market configuration endpoint contracts."""

from __future__ import annotations

import pytest

from api.routers.market import market_config
from bulls.core.tenancy import Tenant


@pytest.mark.asyncio
async def test_market_config_preserves_dse_defaults() -> None:
    tenant = Tenant(
        name="bullsofdhaka",
        display_name="Bulls of Dhaka",
        market="DSE",
        locale="bn",
        timezone="Asia/Dhaka",
        domains=["localhost", "bullsofdhaka.com"],
    )

    config = await market_config(tenant)

    assert config.market == "DSE"
    assert config.currency_symbol == "৳"
    assert config.exchange_label_bn == "ডিএসই"
    assert config.exchange_name_bn == "ঢাকা স্টক এক্সচেঞ্জ"
    assert config.open_time == "10:00"
    assert config.close_time == "14:30"
    assert config.default_locale == "bn"
    assert config.features["dse_categories"] is True
    assert config.features["sec_filings"] is False


@pytest.mark.asyncio
async def test_market_config_can_describe_us_tenant_without_dse_features() -> None:
    tenant = Tenant(
        name="bullsofusa",
        display_name="Bulls of USA",
        market="US",
        locale="en",
        timezone="America/New_York",
        domains=["us.localhost"],
    )

    config = await market_config(tenant)

    assert config.market == "US"
    assert config.currency_symbol == "$"
    assert config.exchange_label_bn == "যুক্তরাষ্ট্রের শেয়ারবাজার"
    assert config.open_time == "09:30"
    assert config.close_time == "16:00"
    assert config.settlement_cycle == "T+1"
    assert config.features["dse_categories"] is False
    assert config.features["shareholding_breakdown"] is False
    assert config.features["sec_filings"] is True
