"""Market profile contracts shared across API, ingestion, and UI-facing metadata."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from pydantic import ValidationError

from bulls.core.markets import format_money_millions, format_price, get_market_profile
from bulls.core.tenancy import Tenant, TenantRegistry


def test_dse_profile_preserves_current_product_defaults() -> None:
    dse = get_market_profile("DSE")

    assert dse.exchange_code == "DSE"
    assert dse.exchange_label("bn") == "ডিএসই"
    assert dse.exchange_name_label("bn") == "ঢাকা স্টক এক্সচেঞ্জ"
    assert dse.currency_code == "BDT"
    assert dse.currency_symbol == "৳"
    assert dse.timezone == "Asia/Dhaka"
    assert dse.timezone_label == "BDT"
    assert dse.place_label("bn") == "ঢাকা"
    assert dse.open_time == dt.time(10, 0)
    assert dse.close_time == dt.time(14, 30)
    assert dse.trading_isoweekdays == frozenset({7, 1, 2, 3, 4})
    assert dse.settlement_cycle == "T+2"
    assert dse.benchmark_label == "DSEX"
    assert dse.features.dse_categories
    assert dse.features.shareholding_breakdown
    assert dse.features.interpreted_analytics
    assert dse.features.price_alerts
    assert dse.price_alert_evaluation == "delayed_quote"
    assert format_price(123.4, "DSE") == "৳123.4"
    assert format_money_millions(5, "DSE") == "৳50L"
    assert format_money_millions(12.5, "DSE") == "৳1.2cr"
    assert format_money_millions(1250, "DSE", style="market_cap") == "৳125 Cr"


def test_us_profile_is_opt_in_and_does_not_inherit_dse_features() -> None:
    us = get_market_profile("US")

    assert us.currency_code == "USD"
    assert us.exchange_label("bn") == "যুক্তরাষ্ট্রের শেয়ারবাজার"
    assert us.currency_symbol == "$"
    assert us.timezone == "America/New_York"
    assert us.timezone_label == "ET"
    assert us.place_label("en") == "New York"
    assert us.open_time == dt.time(9, 30)
    assert us.close_time == dt.time(16, 0)
    assert us.trading_isoweekdays == frozenset({1, 2, 3, 4, 5})
    assert us.settlement_cycle == "T+1"
    assert us.benchmark_label == "SPY (S&P 500 ETF)"
    assert not us.features.dse_categories
    assert not us.features.shareholding_breakdown
    assert us.features.sec_filings
    assert us.features.institutional_holdings
    assert us.features.curated_screens
    assert us.features.company_fundamentals
    assert us.features.learning_quiz
    assert us.features.strategy_scanner
    assert us.features.interpreted_analytics
    assert us.features.price_alerts
    assert us.features.automated_desks
    assert us.price_alert_evaluation == "session_close"
    assert format_price(123.4, "US") == "$123.40"
    assert format_money_millions(500, "US") == "$500.0M"
    assert format_money_millions(1250, "US") == "$1.2B"
    assert format_money_millions(500, "US", style="market_cap") == "$500M"


def test_wall_street_tenant_loads_without_changing_default_tenant() -> None:
    tenants_dir = Path(__file__).resolve().parents[3] / "tenants"
    registry = TenantRegistry.from_dir(tenants_dir, default="bullsofdhaka")

    assert registry.resolve("localhost").name == "bullsofdhaka"
    assert registry.resolve("api.bullsofdhaka.com").name == "bullsofdhaka"
    assert registry.resolve("bullsofdhaka-api.bullstreetai.com").name == "bullsofdhaka"
    assert registry.resolve("bullsofwallst.com").name == "bullsofwallst"
    assert registry.resolve("www.bullsofwallst.com").name == "bullsofwallst"
    assert registry.resolve("api.bullsofwallst.com").name == "bullsofwallst"
    assert registry.resolve("wallst.localhost").name == "bullsofwallst"
    assert registry.resolve("wallst.localhost").display_name == "Bulls of Wall Street"
    assert registry.resolve("wallst.localhost").market == "US"
    assert registry.resolve("wallst.localhost").supported_locales == ["en"]
    assert registry.resolve("bullsofdhaka.com").supported_locales == ["bn", "en"]
    assert registry.resolve("api.shared.local", tenant_host="bullsofwallst.com").name == (
        "bullsofwallst"
    )
    assert registry.resolve("api.shared.local", origin="https://www.bullsofwallst.com").name == (
        "bullsofwallst"
    )
    assert registry.resolve(
        "api.shared.local", referer="https://bullsofwallst.com/en/s/AAPL"
    ).name == ("bullsofwallst")
    assert registry.resolve("bullsofdhaka.com", tenant_host="bullsofwallst.com").name == (
        "bullsofdhaka"
    )
    assert registry.resolve_known("unknown.example") is None


def test_tenant_locale_must_be_enabled_and_known() -> None:
    base = {
        "name": "test",
        "display_name": "Test",
        "market": "US",
        "timezone": "America/New_York",
        "site_url": "https://example.com",
        "support_email": "hello@example.com",
        "email_from": "Test <no-reply@example.com>",
        "logo_url": "https://example.com/logo.png",
        "tagline_en": "Test",
        "tagline_bn": "পরীক্ষা",
    }
    with pytest.raises(ValidationError, match="included in supported_locales"):
        Tenant(**base, locale="bn", supported_locales=["en"])
    with pytest.raises(ValidationError, match="unsupported portal locales"):
        Tenant(**base, locale="en", supported_locales=["en", "de"])
