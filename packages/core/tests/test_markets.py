"""Market profile contracts shared across API, ingestion, and UI-facing metadata."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from pydantic import ValidationError

from bulls.core.markets import cap_tier, format_money_millions, format_price, get_market_profile
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
    assert registry.resolve("research.bullsofdhaka.com").name == "bullsofdhaka"
    assert registry.resolve("atlas.bullsofdhaka.com").name == "bullsofdhaka"
    assert registry.resolve("bullsofwallst.com").name == "bullsofwallst"
    assert registry.resolve("www.bullsofwallst.com").name == "bullsofwallst"
    assert registry.resolve("research.bullsofwallst.com").name == "bullsofwallst"
    assert registry.resolve("atlas.bullsofwallst.com").name == "bullsofwallst"
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
    # Registry resolution remains host-first. The API middleware rejects this contradiction
    # before calling a tenant-sensitive route, rather than silently accepting either claim.
    assert registry.resolve("api.bullsofdhaka.com", tenant_host="bullsofwallst.com").name == (
        "bullsofdhaka"
    )
    assert registry.resolve_known("unknown.example") is None
    assert registry.get("bullsofdhaka").research_site_url == "https://research.bullsofdhaka.com"
    assert registry.get("bullsofdhaka").research_alias_urls == [
        "https://atlas.bullsofdhaka.com"
    ]
    assert registry.get("bullsofdhaka").research_api_url == "https://api.bullsofdhaka.com"
    assert registry.get("bullsofwallst").research_site_url == "https://research.bullsofwallst.com"
    assert registry.get("bullsofwallst").research_alias_urls == [
        "https://atlas.bullsofwallst.com"
    ]
    assert registry.get("bullsofwallst").research_api_url == "https://api.bullsofwallst.com"


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
    with pytest.raises(ValidationError, match="research_api_url host"):
        Tenant(
            **base,
            locale="en",
            supported_locales=["en"],
            domains=["example.com"],
            research_api_url="https://api.other.example",
        )
    with pytest.raises(ValidationError, match="research alias hosts"):
        Tenant(
            **base,
            locale="en",
            supported_locales=["en"],
            domains=["example.com"],
            research_alias_urls=["https://atlas.other.example"],
        )


def test_cap_tier_dse_boundaries_are_inclusive_lower_bounds() -> None:
    # ৳1,000 Cr (10,000 mn) is the calibrated large-cap line — exactly on it belongs above.
    assert cap_tier(10_000.0, "DSE") == "large"
    assert cap_tier(9_999.99, "DSE") == "mid"
    assert cap_tier(2_000.0, "DSE") == "mid"
    assert cap_tier(1_999.99, "DSE") == "small"
    assert cap_tier(500.0, "DSE") == "small"
    assert cap_tier(499.99, "DSE") == "micro"
    assert cap_tier(0.01, "DSE") == "micro"
    # DSE deliberately has no mega tier — its largest cap is still "large".
    assert cap_tier(400_000.0, "DSE") == "large"


def test_cap_tier_us_boundaries_include_mega() -> None:
    assert cap_tier(200_000.0, "US") == "mega"
    assert cap_tier(199_999.0, "US") == "large"
    assert cap_tier(10_000.0, "US") == "large"
    assert cap_tier(2_000.0, "US") == "mid"
    assert cap_tier(300.0, "US") == "small"
    assert cap_tier(299.0, "US") == "micro"


def test_cap_tier_unclassifiable_caps_return_none_never_a_guess() -> None:
    assert cap_tier(None, "DSE") is None
    assert cap_tier(0.0, "DSE") is None
    assert cap_tier(-15.0, "US") is None
    assert cap_tier(float("nan"), "US") is None
    assert cap_tier(float("inf"), "US") is None
    with pytest.raises(ValueError, match="Unknown market profile"):
        cap_tier(1_000.0, "LSE")


def test_us_onboarding_bands_derive_from_canonical_tiers() -> None:
    # Guard against the two threshold systems drifting apart again (the reason cap_tier exists).
    from ingestion.universe_discovery import DiscoveryPolicy

    us = dict(get_market_profile("US").cap_tiers)
    policy = DiscoveryPolicy()
    assert policy.micro_cap_upper_mn == us["small"]
    assert policy.small_cap_upper_mn == us["mid"]
    assert policy.max_market_cap_mn == us["large"]
