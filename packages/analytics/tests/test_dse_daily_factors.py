import datetime as dt

from bulls.analytics.dse_daily_factors import (
    FACTOR_SPECS,
    DividendPoint,
    FundamentalRecord,
    fundamental_features,
    generate_factor_signals,
)
from bulls.analytics.dse_edges import EdgeBar, ExecutionPolicy


def _bars(code_index: int, *, low_turnover: bool = False) -> list[EdgeBar]:
    start = dt.date(2024, 1, 1)
    result = []
    for index in range(180):
        trend = 1 + index * (0.001 + code_index * 0.00002)
        wobble = ((index % 5) - 2) * (0.0005 + code_index * 0.00001)
        close = 100 * (trend + wobble)
        result.append(
            EdgeBar(
                date=start + dt.timedelta(days=index),
                open=close * 0.999,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=100 if low_turnover else 100_000,
            )
        )
    return result


def test_daily_factor_signals_use_the_next_market_session_and_skip_illiquid_names() -> None:
    by_code = {f"CODE{index:02d}": _bars(index) for index in range(25)}
    by_code["ILLIQUID"] = _bars(1, low_turnover=True)
    market = {bar.date: 5_000 + index for index, bar in enumerate(by_code["CODE00"])}
    signals = generate_factor_signals(
        by_code=by_code,
        market_closes=market,
        financials={},
        dividends={},
        spec=FACTOR_SPECS["momentum_daily_control"],
        policy=ExecutionPolicy(minimum_trailing_value=1_000_000),
    )

    assert signals
    assert all(signal.entry_date == signal.signal_date + dt.timedelta(days=1) for signal in signals)
    assert all(signal.code != "ILLIQUID" for signal in signals)


def test_factor_signal_is_skipped_when_the_next_security_bar_is_not_the_next_market_day() -> None:
    by_code = {f"CODE{index:02d}": _bars(index) for index in range(25)}
    first_signal_date = by_code["CODE00"][126].date
    missing_next = first_signal_date + dt.timedelta(days=1)
    by_code["CODE24"] = [bar for bar in by_code["CODE24"] if bar.date != missing_next]
    market = {bar.date: 5_000 + index for index, bar in enumerate(by_code["CODE00"])}
    signals = generate_factor_signals(
        by_code=by_code,
        market_closes=market,
        financials={},
        dividends={},
        spec=FACTOR_SPECS["momentum_daily_control"],
        policy=ExecutionPolicy(minimum_trailing_value=1_000_000),
    )

    assert not any(
        signal.code == "CODE24" and signal.signal_date == first_signal_date
        for signal in signals
    )


def test_quality_value_uses_a_two_year_fundamental_lag() -> None:
    financials = {
        "SAFE": [
            FundamentalRecord(fiscal_year=2022, eps=5, nav_per_share=50),
            FundamentalRecord(fiscal_year=2023, eps=6, nav_per_share=55),
            FundamentalRecord(fiscal_year=2024, eps=100, nav_per_share=100),
        ]
    }
    features = fundamental_features(
        code="SAFE",
        price=60,
        signal_date=dt.date(2025, 6, 1),
        financials=financials,
        dividends={"SAFE": [DividendPoint(year=2023, cash_pct=10)]},
    )

    assert features is not None
    assert features[-1] == 2023
    assert features[0] == 10
