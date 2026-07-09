"""Market profile contracts shared across API, ingestion, and UI-facing metadata."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from bulls.core.markets import format_price, get_market_profile
from bulls.core.tenancy import TenantRegistry


def test_dse_profile_preserves_current_product_defaults() -> None:
    dse = get_market_profile("DSE")

    assert dse.exchange_code == "DSE"
    assert dse.exchange_label("bn") == "ডিএসই"
    assert dse.exchange_name_label("bn") == "ঢাকা স্টক এক্সচেঞ্জ"
    assert dse.currency_code == "BDT"
    assert dse.currency_symbol == "৳"
    assert dse.timezone == "Asia/Dhaka"
    assert dse.open_time == dt.time(10, 0)
    assert dse.close_time == dt.time(14, 30)
    assert dse.trading_isoweekdays == frozenset({7, 1, 2, 3, 4})
    assert dse.settlement_cycle == "T+2"
    assert dse.benchmark_label == "DSEX"
    assert dse.features.dse_categories
    assert dse.features.shareholding_breakdown
    assert format_price(123.4, "DSE") == "৳123.4"


def test_us_profile_is_opt_in_and_does_not_inherit_dse_features() -> None:
    us = get_market_profile("US")

    assert us.currency_code == "USD"
    assert us.exchange_label("bn") == "যুক্তরাষ্ট্রের শেয়ারবাজার"
    assert us.currency_symbol == "$"
    assert us.timezone == "America/New_York"
    assert us.open_time == dt.time(9, 30)
    assert us.close_time == dt.time(16, 0)
    assert us.trading_isoweekdays == frozenset({1, 2, 3, 4, 5})
    assert us.settlement_cycle == "T+1"
    assert us.benchmark_label == "S&P 500"
    assert not us.features.dse_categories
    assert not us.features.shareholding_breakdown
    assert us.features.sec_filings
    assert format_price(123.4, "US") == "$123.40"


def test_dormant_us_tenant_loads_without_changing_default_tenant() -> None:
    tenants_dir = Path(__file__).resolve().parents[3] / "tenants"
    registry = TenantRegistry.from_dir(tenants_dir, default="bullsofdhaka")

    assert registry.resolve("localhost").name == "bullsofdhaka"
    assert registry.resolve("us.localhost").name == "bullsofusa"
    assert registry.resolve("us.localhost").market == "US"
