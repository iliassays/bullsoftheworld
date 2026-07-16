from __future__ import annotations

import datetime as dt

from bulls.analytics import STRATEGIES, Snapshot
from ingestion.agent_trader import _previous_trading_day, _rank_archived_entries


def _snapshot(code: str, *, change_pct: float = 0.5) -> Snapshot:
    return Snapshot(
        code=code,
        sector="Test",
        category="A",
        ltp=100.0,
        change_pct=change_pct,
        quote_as_of=dt.datetime(2026, 7, 19, 4, 0, tzinfo=dt.UTC),
        last_close=99.5,
        rsi_14=40.0,
        pct_from_52w_high=-45.0,
        pct_from_52w_low=10.0,
        pe_ratio=10.0,
        pb_ratio=1.0,
        pe_vs_sector=0.7,
        roe=15.0,
        eps_growth_yoy=5.0,
        dividend_yield=2.0,
        volatility=25.0,
        cmf_20=0.0,
        obv_slope=0.0,
        institute_delta=0.0,
        foreign_delta=0.0,
        rel_volume_5d=1.0,
        relative_volume=1.0,
        avg_volume_20=100_000.0,
        market_cap_mn=1_000.0,
    )


def _decision(code: str, score: int) -> dict:
    return {
        "code": code,
        "score": score,
        "below_high": -45,
        "pe": 10.0,
        "roe": 15,
    }


def test_exact_strategy_policy_matches_published_scheme_three() -> None:
    spec = STRATEGIES["quality_reversal_eod"]

    assert spec.entry_source == "hedge_daily_archive"
    assert spec.stop_loss_pct == -10.0
    assert spec.take_profit_pct == 25.0
    assert spec.max_holding_sessions == 63
    assert spec.max_positions == 10
    assert spec.position_pct == 0.10


def test_archived_entries_preserve_conviction_order_and_execution_guards() -> None:
    snapshots = {
        "LOW": _snapshot("LOW"),
        "HIGH": _snapshot("HIGH"),
        "LOCKED": _snapshot("LOCKED", change_pct=8.5),
    }
    decisions = [
        _decision("LOW", 60),
        _decision("LOCKED", 99),
        _decision("HIGH", 90),
    ]

    ranked = _rank_archived_entries(
        snapshots,
        decisions,
        as_of_date=dt.date(2026, 7, 16),
        held={"LOW"},
    )

    assert [snapshot.code for snapshot, _reason in ranked] == ["HIGH"]
    assert "2026-07-16" in ranked[0][1]
    assert "conviction 90/100" in ranked[0][1]


def test_previous_trading_day_skips_dse_weekend() -> None:
    assert _previous_trading_day(dt.date(2026, 7, 19), "DSE") == dt.date(2026, 7, 16)
