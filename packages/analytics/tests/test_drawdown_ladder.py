"""Tests for the two-rung drawdown ladder (Phase 15 L2 risk grammar)."""

from __future__ import annotations

import pytest

from bulls.analytics.drawdown_ladder import (
    LADDER_PRESETS,
    DrawdownLadder,
    LadderState,
    apply_drawdown_ladder,
    clear_freeze,
)

_MODERATE = LADDER_PRESETS["moderate"]  # halve at 8%, flatten at 12%


def _act(drawdown_pct: float, *, frozen: bool = False):
    return apply_drawdown_ladder(
        drawdown_pct=drawdown_pct, state=LadderState(frozen=frozen), ladder=_MODERATE
    )


# --- validation ----------------------------------------------------------------------------


def test_ladder_rejects_unordered_thresholds() -> None:
    with pytest.raises(ValueError):
        DrawdownLadder(halve_at_pct=0.12, flatten_at_pct=0.08)


def test_ladder_rejects_nonpositive_thresholds() -> None:
    with pytest.raises(ValueError):
        DrawdownLadder(halve_at_pct=0.0, flatten_at_pct=0.10)


def test_negative_drawdown_is_rejected() -> None:
    with pytest.raises(ValueError):
        _act(-0.01)


# --- the three rungs -----------------------------------------------------------------------


def test_shallow_drawdown_keeps_full_exposure() -> None:
    action = _act(0.05)
    assert action.gross_multiplier == 1.0
    assert action.rung == "full"
    assert action.frozen is False


def test_middle_rung_halves_exposure() -> None:
    action = _act(0.09)  # between 8% and 12%
    assert action.gross_multiplier == 0.5
    assert action.rung == "halved"
    assert action.frozen is False


def test_boundary_at_halve_threshold_halves() -> None:
    # The threshold is inclusive: exactly 8% trips the halve rung.
    action = _act(0.08)
    assert action.rung == "halved"


def test_flatten_rung_zeroes_and_freezes() -> None:
    action = _act(0.13)
    assert action.gross_multiplier == 0.0
    assert action.rung == "flattened_frozen"
    assert action.frozen is True


def test_boundary_at_flatten_threshold_flattens() -> None:
    action = _act(0.12)
    assert action.rung == "flattened_frozen"
    assert action.frozen is True


# --- the sticky freeze (the whole point) ---------------------------------------------------


def test_freeze_persists_through_full_recovery() -> None:
    # Book fully recovered (0% drawdown) but still frozen: exposure stays at zero.
    action = _act(0.0, frozen=True)
    assert action.gross_multiplier == 0.0
    assert action.rung == "flattened_frozen"
    assert action.frozen is True


def test_cleared_freeze_restores_exposure_when_book_is_healthy() -> None:
    cleared = clear_freeze(LadderState(frozen=True))
    assert cleared.frozen is False
    action = apply_drawdown_ladder(drawdown_pct=0.03, state=cleared, ladder=_MODERATE)
    assert action.gross_multiplier == 1.0
    assert action.frozen is False


def test_cleared_freeze_refreezes_if_still_in_deep_drawdown() -> None:
    # Clearing the freeze while the book is still below its flatten rung must not let it trade
    # through the loss — the next evaluation re-freezes immediately.
    cleared = clear_freeze(LadderState(frozen=True))
    action = apply_drawdown_ladder(drawdown_pct=0.15, state=cleared, ladder=_MODERATE)
    assert action.rung == "flattened_frozen"
    assert action.frozen is True


# --- presets -------------------------------------------------------------------------------


def test_presets_are_ordered_by_aggressiveness() -> None:
    con, mod, agg = (LADDER_PRESETS[k] for k in ("conservative", "moderate", "aggressive"))
    assert con.halve_at_pct < mod.halve_at_pct < agg.halve_at_pct
    assert con.flatten_at_pct < mod.flatten_at_pct < agg.flatten_at_pct
    # Every preset keeps the halve rung strictly above (shallower than) its flatten rung.
    for ladder in (con, mod, agg):
        assert ladder.halve_at_pct < ladder.flatten_at_pct
