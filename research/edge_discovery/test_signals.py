"""Tests for the data-quality guard.

    .venv/bin/python -m pytest research/edge_discovery/test_signals.py

This guard exists because its absence nearly produced a strategy. A microcap detector read
+98% over 21 sessions; the number was arithmetically correct and economically meaningless,
because sub-penny quoting and zero-volume sessions were setting the mean. Applying the guard
moved the whole-panel 21-session mean from 4.6% to 0.99% — the difference between an implausible
70%/year and an ordinary 12%/year — so these two conditions were carrying the entire artefact.
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

# research/ is not an installed package; it is run in place.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from edge_discovery import signals


def _frame(**cols) -> pl.DataFrame:
    base = {
        "close": [10.0],
        "volume": [100_000],
        "liq_decile": [9],
        "bars_seen": [500],
        "adv_20": [5_000_000.0],
        "vol_60": [0.02],
    }
    base.update({k: [v] for k, v in cols.items()})
    return pl.DataFrame(base)


def test_sub_penny_rows_are_excluded() -> None:
    """PPCB at $0.01 ticking to $0.02 printed +4,166,567% over 21 sessions."""
    assert _frame(close=0.01).filter(signals.tradeable()).height == 0
    assert _frame(close=0.99).filter(signals.tradeable()).height == 0


def test_zero_volume_rows_are_excluded() -> None:
    """A carried-forward close is a quote, not a trade; a fill cannot be assumed."""
    assert _frame(volume=0).filter(signals.tradeable()).height == 0


def test_ordinary_rows_survive() -> None:
    assert _frame().filter(signals.tradeable()).height == 1
    assert _frame(close=1.00).filter(signals.tradeable()).height == 1


def test_eligible_cannot_be_lowered_into_the_noise_floor() -> None:
    """A caller reaching for microcaps must not be able to reach sub-penny rows as well."""
    penny = _frame(close=0.02, liq_decile=9)
    assert penny.filter(signals.eligible(min_price=0.0, min_bars=0)).height == 0


def test_eligible_still_admits_genuine_microcaps() -> None:
    micro = _frame(close=1.50, liq_decile=4, adv_20=800_000.0)
    assert micro.filter(signals.eligible(min_liq_decile=4, min_price=1.0, min_bars=0)).height == 1
