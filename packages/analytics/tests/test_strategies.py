"""Strategy rules: entry/exit decisions over explicit synthetic snapshots.

Each test builds a snapshot that clearly satisfies (or clearly violates) one strategy's published
rules — thresholds themselves are asserted only via behavior, so recalibrating a number changes
one place, not the tests. Circuit-lock guards and universe gates get their own tests because a
bug there means simulated fills that couldn't have happened on the real exchange.
"""

from __future__ import annotations

import dataclasses
import datetime as dt

from bulls.analytics.strategies import (
    STRATEGIES,
    Snapshot,
    entry_reason,
    exit_reason,
    rank_entries,
    universe_ok,
)

_AS_OF = dt.datetime(2026, 7, 5, 11, 0, tzinfo=dt.UTC)


def snap(**over) -> Snapshot:
    """A liquid, mid-range, 'nothing interesting' A-category stock; tests override what matters."""
    base = dict(
        code="TEST",
        sector="Bank",
        category="A",
        ltp=100.0,
        change_pct=0.5,
        quote_as_of=_AS_OF,
        last_close=99.5,
        rsi_14=50.0,
        pct_from_52w_high=-15.0,
        pct_from_52w_low=30.0,
        pe_ratio=12.0,
        pb_ratio=1.2,
        pe_vs_sector=1.0,
        roe=12.0,
        eps_growth_yoy=5.0,
        dividend_yield=2.0,
        volatility=25.0,
        cmf_20=0.0,
        obv_slope=0.0,
        institute_delta=0.0,
        foreign_delta=0.0,
        rel_volume_5d=1.0,
        relative_volume=1.0,
        avg_volume_20=200_000.0,
        market_cap_mn=2_000.0,
    )
    base.update(over)
    return Snapshot(**base)


# --- universe gates -------------------------------------------------------------------------


def test_universe_rejects_illiquid_small_and_z_category():
    assert universe_ok(snap())
    assert not universe_ok(snap(avg_volume_20=1_000.0))  # ~1 lakh/day turnover: too thin
    assert not universe_ok(snap(market_cap_mn=200.0))  # under 50 crore
    assert not universe_ok(snap(category="Z"))
    assert not universe_ok(snap(avg_volume_20=None))


def test_buys_blocked_at_upper_circuit_and_sells_blocked_at_lower():
    """A stock locked at its circuit limit has no counterparty — a simulated fill there would be
    fake. Entry must refuse near the upper lock even if the setup qualifies; exits must refuse
    near the lower lock even if the stop is hit."""
    rebound = snap(
        pct_from_52w_high=-45.0,
        pct_from_52w_low=8.0,
        pe_ratio=10.0,
        rsi_14=32.0,
        change_pct=8.5,
        relative_volume=2.0,
    )
    assert entry_reason("rebound", rebound) is None
    stopped = snap(change_pct=-8.5)
    assert exit_reason("rebound", stopped, avg_cost=120.0) is None  # -17% but limit-locked


# --- entries per strategy -------------------------------------------------------------------


def test_rebound_entry_needs_washout_quality_and_uptick():
    good = snap(
        pct_from_52w_high=-45.0,
        pct_from_52w_low=8.0,
        pe_ratio=10.0,
        rsi_14=32.0,
        change_pct=1.5,
        relative_volume=1.5,
    )
    assert entry_reason("rebound", good)
    assert entry_reason("rebound", dataclasses.replace(good, pct_from_52w_high=-20.0)) is None
    assert entry_reason("rebound", dataclasses.replace(good, pe_ratio=None)) is None  # loss-maker
    assert entry_reason("rebound", dataclasses.replace(good, change_pct=-1.0)) is None  # no uptick


def test_value_entry_needs_cheap_vs_sector_and_no_value_trap():
    good = snap(pe_vs_sector=0.6, pe_ratio=8.0, pb_ratio=0.9, roe=10.0)
    assert entry_reason("value", good)
    assert entry_reason("value", dataclasses.replace(good, pe_vs_sector=0.95)) is None
    assert entry_reason("value", dataclasses.replace(good, roe=3.0)) is None  # value trap gate


def test_quality_entry_needs_roe_growth_and_sane_price():
    good = snap(roe=22.0, eps_growth_yoy=12.0, pe_ratio=18.0)
    assert entry_reason("quality", good)
    assert entry_reason("quality", dataclasses.replace(good, roe=9.0)) is None
    assert entry_reason("quality", dataclasses.replace(good, eps_growth_yoy=-5.0)) is None
    assert entry_reason("quality", dataclasses.replace(good, pe_ratio=40.0)) is None


def test_dividend_entry_needs_yield_and_calm():
    good = snap(dividend_yield=5.5, volatility=22.0, pe_ratio=10.0)
    assert entry_reason("dividend", good)
    assert entry_reason("dividend", dataclasses.replace(good, dividend_yield=1.5)) is None
    assert entry_reason("dividend", dataclasses.replace(good, volatility=70.0)) is None


def test_accumulation_entry_needs_flow_and_ownership_confirmation():
    good = snap(cmf_20=0.18, obv_slope=0.4, institute_delta=0.6, rel_volume_5d=1.3)
    assert entry_reason("accumulation", good)
    assert entry_reason("accumulation", dataclasses.replace(good, cmf_20=0.02)) is None
    assert (
        entry_reason(
            "accumulation",
            dataclasses.replace(good, institute_delta=0.0, foreign_delta=0.0),
        )
        is None
    )


# --- exits ----------------------------------------------------------------------------------


def test_stop_loss_fires_for_every_strategy():
    s = snap(ltp=88.0, change_pct=-2.0)
    for key in STRATEGIES:
        assert exit_reason(key, s, avg_cost=100.0)  # -12% is at/below every stop


def test_rebound_take_profit_and_rsi_exit():
    assert exit_reason("rebound", snap(ltp=121.0), avg_cost=100.0)  # +21% >= +20% target
    assert exit_reason("rebound", snap(ltp=110.0, rsi_14=70.0), avg_cost=100.0)  # recovered
    assert exit_reason("rebound", snap(ltp=110.0, rsi_14=55.0), avg_cost=100.0) is None


def test_value_exits_when_no_longer_cheap():
    assert exit_reason("value", snap(pe_vs_sector=1.2), avg_cost=100.0)
    assert exit_reason("value", snap(pe_vs_sector=0.7), avg_cost=100.0) is None


def test_dividend_exits_when_yield_compresses():
    assert exit_reason("dividend", snap(dividend_yield=1.8), avg_cost=100.0)
    assert exit_reason("dividend", snap(dividend_yield=4.5), avg_cost=100.0) is None


def test_accumulation_exits_on_distribution():
    assert exit_reason("accumulation", snap(cmf_20=-0.12), avg_cost=100.0)
    assert exit_reason("accumulation", snap(cmf_20=0.1), avg_cost=100.0) is None


def test_missing_analytics_never_crashes_and_never_enters():
    bare = snap(
        rsi_14=None,
        pe_ratio=None,
        pb_ratio=None,
        pe_vs_sector=None,
        roe=None,
        eps_growth_yoy=None,
        dividend_yield=None,
        volatility=None,
        cmf_20=None,
        obv_slope=None,
        institute_delta=None,
        foreign_delta=None,
        rel_volume_5d=None,
        relative_volume=None,
        pct_from_52w_high=None,
        pct_from_52w_low=None,
    )
    for key in STRATEGIES:
        assert entry_reason(key, bare) is None
        assert exit_reason(key, bare, avg_cost=100.0) is None  # no stop either: ltp still known?
    # ltp IS known, so the stop must still work even with no analytics at all:
    assert exit_reason("value", dataclasses.replace(bare, ltp=80.0), avg_cost=100.0)


# --- ranking --------------------------------------------------------------------------------


def test_rank_entries_orders_best_first_and_skips_held_codes():
    a = snap(code="AAA", pe_vs_sector=0.5, pe_ratio=6.0, pb_ratio=0.8, roe=10.0)
    b = snap(code="BBB", pe_vs_sector=0.75, pe_ratio=9.0, pb_ratio=1.0, roe=10.0)
    c = snap(code="CCC", pe_vs_sector=1.4)  # not a value entry at all
    ranked = rank_entries("value", [c, b, a], held={"BBB"})
    assert [s.code for s, _reason in ranked] == ["AAA"]
    ranked_all = rank_entries("value", [b, a], held=set())
    assert [s.code for s, _ in ranked_all] == ["AAA", "BBB"]


# --- second wave: lowpaidup / graham / buffett ------------------------------------------------


def test_lowpaidup_entry_needs_scarce_supply_with_quality_floor():
    good = snap(paid_up_capital_mn=300.0, pe_ratio=14.0, rsi_14=55.0)
    assert entry_reason("lowpaidup", good)
    assert entry_reason("lowpaidup", dataclasses.replace(good, paid_up_capital_mn=2_000.0)) is None
    assert entry_reason("lowpaidup", dataclasses.replace(good, pe_ratio=None)) is None  # loss-maker
    assert entry_reason("lowpaidup", dataclasses.replace(good, rsi_14=75.0)) is None  # too hot
    assert entry_reason("lowpaidup", dataclasses.replace(good, paid_up_capital_mn=None)) is None


def test_lowpaidup_exits_when_overheated():
    assert exit_reason("lowpaidup", snap(rsi_14=80.0), avg_cost=100.0)
    assert exit_reason("lowpaidup", snap(rsi_14=60.0), avg_cost=100.0) is None


def test_graham_entry_tracks_the_lens_score():
    # pe_vs_sector<0.75 (+2), pe<=12 (+1), pb<1.2 (+1), yield>=3 (+1) -> 10/10
    good = snap(pe_vs_sector=0.6, pe_ratio=8.0, pb_ratio=0.9, roe=12.0, dividend_yield=4.0)
    reason = entry_reason("graham", good)
    assert reason and "/10" in reason
    # Neutral-priced stock scores ~5 -> no entry.
    assert entry_reason("graham", snap()) is None


def test_graham_exits_when_score_decays():
    rich = snap(pe_vs_sector=1.4, pe_ratio=30.0, pb_ratio=3.5)  # 5-2-2-1 -> 0/10
    assert exit_reason("graham", rich, avg_cost=100.0)
    cheap = snap(pe_vs_sector=0.6, pe_ratio=8.0, pb_ratio=0.9, dividend_yield=4.0)
    assert exit_reason("graham", cheap, avg_cost=100.0) is None


def test_buffett_entry_and_exit_track_the_lens_score():
    # roe>=20 (+3), growth>=15 (+2), dividend (+1) -> 10/10 (trend intact)
    good = snap(roe=25.0, eps_growth_yoy=20.0, dividend_yield=2.0, above_sma_200=True)
    assert entry_reason("buffett", good)
    # Decayed fundamentals: roe 8 (-1), growth -5 (-1), dividend (+1) -> 4/10: exit fires.
    bad = dataclasses.replace(good, roe=8.0, eps_growth_yoy=-5.0, dividend_yield=2.0)
    assert entry_reason("buffett", bad) is None
    assert exit_reason("buffett", bad, avg_cost=100.0)


def test_new_strategies_respect_universe_gates_too():
    good = snap(paid_up_capital_mn=300.0, pe_ratio=14.0, rsi_14=55.0, category="Z")
    assert entry_reason("lowpaidup", good) is None  # Z-category stays untouchable


def test_archived_quality_strategy_never_reconstructs_entry_from_intraday_fields():
    good = snap(
        pct_from_52w_high=-45.0,
        pct_from_52w_low=8.0,
        pe_ratio=10.0,
        rsi_14=32.0,
        change_pct=1.5,
        relative_volume=1.5,
    )
    assert entry_reason("quality_reversal_eod", good) is None
