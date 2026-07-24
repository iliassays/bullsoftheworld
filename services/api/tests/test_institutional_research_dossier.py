from __future__ import annotations

import datetime as dt
from decimal import Decimal

from api.institutional_research.dossier import (
    _adjusted_ohlc,
    _institutional_disclosure,
    _reported_ownership,
    _short_activity,
)
from bulls.core.models import (
    DailyBar,
    InstitutionalHoldingSummary,
    ShareholdingSnapshot,
    ShortVolumeDaily,
)


def test_adjusted_ohlc_applies_the_same_split_factor_to_the_complete_bar() -> None:
    row = DailyBar(
        market="US",
        code="SPLT",
        date=dt.date(2026, 7, 14),
        open=98,
        high=104,
        low=96,
        close=100,
        adjusted_close=50,
        volume=1000,
    )

    assert _adjusted_ohlc(row) == (49.0, 52.0, 48.0, 50.0)


def test_reported_ownership_uses_percentage_point_changes_and_reconciles_total() -> None:
    latest = ShareholdingSnapshot(
        market="DSE",
        code="BSC",
        as_of_date=dt.date(2026, 6, 30),
        sponsor_director=30.0,
        govt=10.0,
        institute=25.0,
        foreign_pct=5.0,
        public=30.0,
    )
    previous = ShareholdingSnapshot(
        market="DSE",
        code="BSC",
        as_of_date=dt.date(2026, 5, 31),
        sponsor_director=30.0,
        govt=10.0,
        institute=23.5,
        foreign_pct=5.5,
        public=31.0,
    )

    result = _reported_ownership([latest, previous])

    assert result is not None
    assert result.composition_total_pct == 100.0
    changes = {item.key: item.change_pp for item in result.categories}
    assert changes["institutional"] == 1.5
    assert changes["foreign"] == -0.5
    assert "do not prove buying or selling" in result.interpretation


def test_13f_breadth_excludes_unchanged_managers_and_states_the_delay() -> None:
    row = InstitutionalHoldingSummary(
        market="US",
        code="NXTC",
        report_date=dt.date(2026, 3, 31),
        prior_report_date=dt.date(2025, 12, 31),
        latest_filing_date=dt.date(2026, 5, 15),
        managers_count=12,
        total_shares=1_000_000,
        total_value_usd=8_000_000.0,
        new_positions=3,
        increased_positions=2,
        reduced_positions=1,
        exited_positions=1,
        unchanged_positions=5,
        net_share_change=100_000,
        net_change_pct=11.11,
        source_url="https://www.sec.gov/",
        updated_at=dt.datetime(2026, 5, 15, tzinfo=dt.UTC),
    )

    result = _institutional_disclosure(row)

    assert result is not None
    assert result.adding_managers == 5
    assert result.reducing_managers == 2
    assert result.net_breadth_pct == 42.86
    assert any("45 days" in limitation for limitation in result.limitations)
    assert "not a live fund-flow" in result.interpretation


def test_finra_short_activity_does_not_double_count_short_exempt_volume() -> None:
    latest = ShortVolumeDaily(
        market="US",
        code="VEEE",
        date=dt.date(2026, 7, 14),
        short_volume=Decimal("600"),
        short_exempt_volume=Decimal("100"),
        total_volume=Decimal("1000"),
        source="finra_cnms",
    )
    baseline = [
        ShortVolumeDaily(
            market="US",
            code="VEEE",
            date=dt.date(2026, 7, day),
            short_volume=Decimal("400"),
            short_exempt_volume=Decimal("50"),
            total_volume=Decimal("1000"),
            source="finra_cnms",
        )
        for day in range(1, 6)
    ]

    result = _short_activity([latest, *baseline])

    assert result is not None
    assert result.short_marked_share_pct == 60.0
    assert result.average_20_pct == 40.0
    assert result.deviation_pp == 20.0
    assert "cannot establish bearish positioning" in result.interpretation
