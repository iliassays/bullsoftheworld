from __future__ import annotations

import datetime as dt

from api.routers.company import _financial_health, _quarter_rows
from bulls.core.models import SecFinancialFact


def _fact(metric: str, value: float, end: dt.date, *, period_type: str = "quarter"):
    return SecFinancialFact(
        market="US",
        code="TEST",
        metric=metric,
        value=value,
        unit="USD",
        period_start=end - dt.timedelta(days=90) if period_type != "instant" else None,
        period_end=end,
        period_type=period_type,
        fiscal_year=end.year,
        fiscal_period="Q1",
        form="10-Q",
        filed_at=end + dt.timedelta(days=35),
        accession_number="0000000001-26-000001",
        taxonomy="us-gaap",
        source_concept=metric,
        frame=None,
        source_url="https://www.sec.gov/example",
    )


def test_financial_health_uses_four_quarters_and_cash_flow_identity() -> None:
    ends = [
        dt.date(2025, 6, 30),
        dt.date(2025, 9, 30),
        dt.date(2025, 12, 31),
        dt.date(2026, 3, 31),
    ]
    facts = []
    for end in ends:
        facts.extend(
            [
                _fact("revenue", 100_000_000, end),
                _fact("net_income", 10_000_000, end),
                _fact("operating_cash_flow", 15_000_000, end),
                _fact("capital_expenditure", 4_000_000, end),
            ]
        )
    facts.extend(
        [
            _fact("current_assets", 200_000_000, ends[-1], period_type="instant"),
            _fact("current_liabilities", 100_000_000, ends[-1], period_type="instant"),
            _fact("equity", 300_000_000, ends[-1], period_type="instant"),
            _fact("debt_noncurrent", 90_000_000, ends[-1], period_type="instant"),
        ]
    )

    health = _financial_health(facts)

    assert health.revenue_ttm_mn == 400
    assert health.net_income_ttm_mn == 40
    assert health.profit_margin_pct == 10
    assert health.free_cash_flow_ttm_mn == 44
    assert health.current_ratio == 2
    assert health.debt_to_equity == 0.3


def test_quarter_rows_keep_periods_separate_and_cited() -> None:
    end = dt.date(2026, 3, 31)

    rows = _quarter_rows([_fact("revenue", 100_000_000, end), _fact("eps_diluted", 1.25, end)])

    assert rows[0].period_end == "2026-03-31"
    assert rows[0].revenue_mn == 100
    assert rows[0].eps == 1.25
    assert rows[0].source_url == "https://www.sec.gov/example"
