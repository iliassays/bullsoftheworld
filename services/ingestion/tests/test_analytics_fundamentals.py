import datetime as dt
from types import SimpleNamespace

from ingestion.analytics import _comparable_eps_growth, analytics_input_fingerprint


def test_eps_growth_requires_a_positive_comparable_base() -> None:
    assert _comparable_eps_growth(12.0, 10.0) == 20.0
    assert _comparable_eps_growth(8.0, 10.0) == -20.0


def test_loss_base_is_not_presented_as_percentage_growth() -> None:
    assert _comparable_eps_growth(2.0, -2.0) is None
    assert _comparable_eps_growth(-1.0, -2.0) is None
    assert _comparable_eps_growth(2.0, 0.0) is None
    assert _comparable_eps_growth(None, 2.0) is None


def test_analytics_input_fingerprint_changes_with_an_input_revision() -> None:
    bar = SimpleNamespace(
        date=dt.date(2026, 7, 17),
        open=10.0,
        high=11.0,
        low=9.5,
        close=10.5,
        volume=1000,
        adjusted_close=10.5,
    )
    profile = SimpleNamespace(
        sector="Technology",
        outstanding_shares=1_000_000,
        market_cap_mn=10.5,
        free_float_mcap_mn=5.0,
        eps=1.0,
        nav_per_share=4.0,
        face_value=1.0,
    )
    kwargs = {
        "market": "US",
        "code": "TEST",
        "bars": [bar],
        "profile": profile,
        "cash_dividend": (None, 0.1),
        "sector_median_pe": 12.0,
        "ownership": None,
        "eps_growth": 5.0,
    }

    first = analytics_input_fingerprint(**kwargs)
    second = analytics_input_fingerprint(**kwargs)
    revised = analytics_input_fingerprint(**{**kwargs, "eps_growth": 6.0})

    assert first == second
    assert first != revised
    assert len(first) == 64
