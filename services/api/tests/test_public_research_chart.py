from __future__ import annotations

import datetime as dt

from api.routers.market import _public_research_chart
from bulls.analytics.adjustments import AdjustedBar


def _bars(market: str, code: str) -> list[AdjustedBar]:
    start = dt.date(2026, 1, 2)
    rows: list[AdjustedBar] = []
    for index in range(90):
        close = 20.0 + index * 0.15
        rows.append(
            AdjustedBar(
                market=market,
                code=code,
                date=start + dt.timedelta(days=index),
                open=close - 0.05,
                high=close + 0.20,
                low=close - 0.20,
                close=close,
                volume=300_000 if index == 89 else 100_000,
            )
        )
    return rows


def test_public_research_chart_is_a_bounded_completed_session_projection() -> None:
    chart = _public_research_chart("DSE", "TEST", _bars("DSE", "TEST"))

    assert chart.market == "DSE"
    assert chart.code == "TEST"
    assert chart.source_frequency == "completed_daily"
    assert chart.price_basis == "corporate_action_adjusted"
    assert chart.methodology_version == "research-conditions-v1"
    assert {overlay.key for overlay in chart.overlays} == {"ema20", "ema50"}
    assert {condition.key for condition in chart.conditions} == {
        "trend_alignment",
        "participation_expansion",
        "controlled_pullback_context",
    }
    assert next(
        condition for condition in chart.conditions if condition.key == "participation_expansion"
    ).state == "observed"
    assert chart.volume_profile.status == "unavailable"
    assert chart.volume_profile.method == "not_available"
    assert "Daily OHLCV" in chart.volume_profile.reason


def test_same_engine_does_not_mix_market_identity() -> None:
    dse = _public_research_chart("DSE", "SAME", _bars("DSE", "SAME"))
    us = _public_research_chart("US", "SAME", _bars("US", "SAME"))

    assert dse.market == "DSE"
    assert us.market == "US"
    assert [condition.state for condition in dse.conditions] == [
        condition.state for condition in us.conditions
    ]
