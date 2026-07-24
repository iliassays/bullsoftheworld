import datetime as dt

import pytest

from bulls.analytics.factor_reproduction import (
    FactorPricePoint,
    FactorSecurityHistory,
    compare_to_reference,
    parse_french_daily_momentum_csv,
    reproduce_daily_momentum,
)


def _history(
    security_id: str,
    *,
    market_equity: float,
    formation_return: float,
    final_return: float,
) -> FactorSecurityHistory:
    start = dt.date(2024, 1, 1)
    points = []
    for index in range(252):
        formation_progress = min(index, 230) / 230
        close = 10 * (1 + formation_return * formation_progress)
        if index == 251:
            close *= 1 + final_return
        points.append(
            FactorPricePoint(
                date=start + dt.timedelta(days=index),
                adjusted_close=close,
                market_equity=market_equity,
            )
        )
    return FactorSecurityHistory(
        security_id=security_id,
        exchange="NYSE",
        points=points,
    )


def test_reproduces_six_portfolio_momentum_identity() -> None:
    histories = [
        _history("SL", market_equity=10, formation_return=-0.30, final_return=-0.02),
        _history("SN", market_equity=20, formation_return=0.00, final_return=0.00),
        _history("SH", market_equity=30, formation_return=0.30, final_return=0.03),
        _history("BL", market_equity=70, formation_return=-0.20, final_return=-0.01),
        _history("BN", market_equity=80, formation_return=0.01, final_return=0.00),
        _history("BH", market_equity=90, formation_return=0.20, final_return=0.01),
    ]

    result = reproduce_daily_momentum(histories)

    assert len(result.points) == 1
    # 1/2(3% + 1%) - 1/2(-2% + -1%) = 3.5%
    assert result.points[0].return_decimal == pytest.approx(0.035, abs=1e-9)
    assert result.points[0].eligible_securities == 6


def test_reference_comparison_fails_closed_on_short_overlap() -> None:
    histories = [
        _history("SL", market_equity=10, formation_return=-0.30, final_return=-0.02),
        _history("SN", market_equity=20, formation_return=0.00, final_return=0.00),
        _history("SH", market_equity=30, formation_return=0.30, final_return=0.03),
        _history("BL", market_equity=70, formation_return=-0.20, final_return=-0.01),
        _history("BN", market_equity=80, formation_return=0.01, final_return=0.00),
        _history("BH", market_equity=90, formation_return=0.20, final_return=0.01),
    ]
    local = reproduce_daily_momentum(histories)
    reference = {local.points[0].date: local.points[0].return_decimal}

    comparison = compare_to_reference(local, reference)

    assert not comparison.passed
    assert comparison.overlapping_sessions == 1
    assert any("at least 252" in gate for gate in comparison.failed_gates)


def test_parses_official_percent_returns_and_skips_sentinels() -> None:
    payload = """Daily Mom,
20250102,  1.25
20250103, -0.50
20250106,-99.99
Annual Factors: January-December
"""

    parsed = parse_french_daily_momentum_csv(payload)

    assert parsed == {
        dt.date(2025, 1, 2): 0.0125,
        dt.date(2025, 1, 3): -0.005,
    }
