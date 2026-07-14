"""Public market configuration endpoint contracts."""

from __future__ import annotations

import datetime as dt

import pytest

from api.deps import current_locale
from api.routers.market import market_config
from bulls.core.scheduling import analysis_schedule
from bulls.core.tenancy import Tenant


@pytest.mark.asyncio
async def test_market_config_preserves_dse_defaults() -> None:
    tenant = Tenant(
        name="bullsofdhaka",
        display_name="Bulls of Dhaka",
        market="DSE",
        locale="bn",
        supported_locales=["bn", "en"],
        timezone="Asia/Dhaka",
        domains=["localhost", "bullsofdhaka.com"],
        site_url="https://bullsofdhaka.com",
        support_email="hello@bullsofdhaka.com",
        email_from="Bulls of Dhaka <no-reply@bullsofdhaka.com>",
        logo_url="https://bullsofdhaka.com/logo-mark-v2.png",
        tagline_en="Facts, not rumours",
        tagline_bn="তথ্যে চলুন, গুজবে নয়",
        research_beta=False,
        social_url="https://facebook.example/bullsofdhaka",
    )

    config = await market_config(tenant)

    assert config.market == "DSE"
    assert config.currency_symbol == "৳"
    assert config.exchange_label_bn == "ডিএসই"
    assert config.exchange_name_bn == "ঢাকা স্টক এক্সচেঞ্জ"
    assert config.timezone_label == "BDT"
    assert config.place_label_bn == "ঢাকা"
    assert config.open_time == "10:00"
    assert config.close_time == "14:30"
    assert config.compact_money_units[0]["suffix"] == "cr"
    assert config.market_cap_money_units[0]["suffix"] == " Cr"
    assert config.default_locale == "bn"
    assert config.supported_locales == ["bn", "en"]
    assert config.price_alert_evaluation == "delayed_quote"
    assert config.features["dse_categories"] is True
    assert config.features["learning_quiz"] is True
    assert config.features["interpreted_analytics"] is True
    assert config.features["price_alerts"] is True
    assert config.features["intraday_quotes"] is True
    assert config.research_beta is False
    assert config.features["sec_filings"] is False
    assert config.features["strategy_scanner"] is True
    assert config.social_url == "https://facebook.example/bullsofdhaka"


@pytest.mark.asyncio
async def test_market_config_can_describe_us_tenant_without_dse_features() -> None:
    tenant = Tenant(
        name="bullsofwallst",
        display_name="Bulls of Wall Street",
        market="US",
        locale="en",
        supported_locales=["en"],
        timezone="America/New_York",
        domains=["bullsofwallst.com", "www.bullsofwallst.com", "wallst.localhost"],
        site_url="https://bullsofwallst.com",
        support_email="hello@bullsofwallst.com",
        email_from="Bulls of Wall Street <no-reply@bullsofwallst.com>",
        logo_url="https://bullsofwallst.com/logo-mark-v2.png",
        tagline_en="US market intelligence, not noise",
        tagline_bn="যুক্তরাষ্ট্রের বাজার তথ্য, গুজব নয়",
        research_beta=True,
    )

    config = await market_config(tenant)

    assert config.market == "US"
    assert config.default_locale == "en"
    assert config.supported_locales == ["en"]
    assert current_locale(tenant, "bn") == "en"
    assert current_locale(tenant, "en") == "en"
    assert config.tenant_name == "bullsofwallst"
    assert config.brand_name == "Bulls of Wall Street"
    assert config.site_url == "https://bullsofwallst.com"
    assert config.currency_symbol == "$"
    assert config.exchange_label_bn == "যুক্তরাষ্ট্রের শেয়ারবাজার"
    assert config.timezone_label == "ET"
    assert config.place_label_en == "New York"
    assert config.open_time == "09:30"
    assert config.close_time == "16:00"
    assert config.settlement_cycle == "T+1"
    assert config.compact_money_units[0]["suffix"] == "B"
    assert config.market_cap_money_units[1]["suffix"] == "M"
    assert config.features["dse_categories"] is False
    assert config.features["shareholding_breakdown"] is False
    assert config.features["sec_filings"] is True
    assert config.features["institutional_holdings"] is True
    assert config.features["curated_screens"] is True
    assert config.features["company_fundamentals"] is True
    assert config.features["learning_quiz"] is True
    assert config.features["strategy_scanner"] is True
    assert config.features["interpreted_analytics"] is True
    assert config.features["price_alerts"] is True
    assert config.features["automated_desks"] is True
    assert config.price_alert_evaluation == "session_close"
    assert config.features["intraday_quotes"] is False
    assert config.research_beta is True
    assert config.social_url is None


def test_dse_analysis_schedule_distinguishes_processing_window_from_late_data() -> None:
    before_publication = dt.datetime(2026, 7, 12, 11, 0, tzinfo=dt.UTC)  # 17:00 Dhaka
    expected, next_run = analysis_schedule(before_publication, "DSE")

    assert expected == dt.date(2026, 7, 9)
    assert next_run == dt.datetime(2026, 7, 12, 13, 15, tzinfo=dt.UTC)

    after_publication = dt.datetime(2026, 7, 12, 14, 0, tzinfo=dt.UTC)
    expected, next_run = analysis_schedule(after_publication, "DSE")

    assert expected == dt.date(2026, 7, 12)
    assert next_run == dt.datetime(2026, 7, 13, 13, 15, tzinfo=dt.UTC)


def test_us_analysis_schedule_tracks_utc_cron_across_market_timezone() -> None:
    before_publication = dt.datetime(2026, 7, 9, 22, 0, tzinfo=dt.UTC)
    expected, next_run = analysis_schedule(before_publication, "US")

    assert expected == dt.date(2026, 7, 8)
    assert next_run == dt.datetime(2026, 7, 9, 22, 45, tzinfo=dt.UTC)

    after_publication = dt.datetime(2026, 7, 10, 0, 0, tzinfo=dt.UTC)
    expected, next_run = analysis_schedule(after_publication, "US")

    assert expected == dt.date(2026, 7, 9)
    assert next_run == dt.datetime(2026, 7, 10, 22, 45, tzinfo=dt.UTC)
