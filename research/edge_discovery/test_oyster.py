from __future__ import annotations

import datetime as dt
import math

from research.edge_discovery.oyster import (
    OysterResearchBar,
    OysterResearchSpec,
    scan_oyster_events,
)


def _decline_then_retest():
    start = dt.date(2025, 1, 1)
    bars: list[OysterResearchBar] = []
    for index in range(84):
        center = 105.0 - 0.55 * index
        close = center + 4.0 * math.cos(2.0 * math.pi * index / 12.0)
        bars.append(
            OysterResearchBar(
                date=start + dt.timedelta(days=index),
                open=close - 0.2,
                high=close + 0.8,
                low=close - 0.8,
                close=close,
                volume=1_000_000,
            )
        )
    for close, volume in zip(
        (64.0, 62.5, 61.8, 62.4, 62.8),
        (1_100_000, 650_000, 600_000, 550_000, 600_000),
        strict=True,
    ):
        bars.append(
            OysterResearchBar(
                date=start + dt.timedelta(days=len(bars)),
                open=close - 0.2,
                high=close + 0.7,
                low=close - 0.7,
                close=close,
                volume=volume,
            )
        )
    return bars


def _bars():
    base = _decline_then_retest()
    rows = [*base]
    for _index in range(20):
        previous = rows[-1]
        close = previous.close * 1.01
        rows.append(
            OysterResearchBar(
                date=previous.date + dt.timedelta(days=1),
                open=previous.close,
                high=close * 1.01,
                low=previous.close * 0.99,
                close=close,
                volume=800_000,
            )
        )
    return rows


def _spec(**overrides):
    values = {
        "key": "test_oyster",
        "analysis_start": dt.date(2025, 1, 1),
        "minimum_price": 1.0,
        "maximum_price": None,
        "minimum_average_turnover": 100_000.0,
        "maximum_absolute_close_return": None,
    }
    values.update(overrides)
    return OysterResearchSpec(**values)


def test_archives_one_event_per_cross_and_computes_completed_outcomes():
    events = scan_oyster_events("TEST", _bars(), _spec())

    assert len(events) == 1
    event = events[0]
    assert event.signal_date > event.cross_date
    assert event.close_returns[1] is not None
    assert event.close_returns[20] is not None
    assert event.maximum_high_returns[20] is not None
    assert event.minimum_low_returns[20] is not None
    assert event.opportunities["20s_10pct"] is not None


def test_liquidity_and_price_policy_can_abstain():
    assert scan_oyster_events(
        "TEST",
        _bars(),
        _spec(minimum_average_turnover=1_000_000_000.0),
    ) == []
    assert scan_oyster_events("TEST", _bars(), _spec(maximum_price=10.0)) == []


def test_dse_contamination_policy_rejects_large_unadjusted_jump():
    bars = _bars()
    contaminated = [*bars]
    row = contaminated[20]
    contaminated[20] = OysterResearchBar(
        date=row.date,
        open=row.open * 2,
        high=row.high * 2,
        low=row.low * 2,
        close=row.close * 2,
        volume=row.volume,
    )

    assert scan_oyster_events(
        "TEST",
        contaminated,
        _spec(maximum_absolute_close_return=0.35),
    ) == []
