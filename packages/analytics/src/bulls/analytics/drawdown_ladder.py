"""Two-rung drawdown ladder: the book-level risk grammar from Phase 15 (L2).

The institutional study's risk rulebook is graduated and, crucially, *sticky*:

    halve gross exposure at   -6% / -8% / -12% from book high-water mark   (conservative/mod/agg)
    flatten AND freeze at     -10% / -12% / -18%   → freeze needs a written review before re-entry

The point of the ladder (Phase 5 finding 4, Phase 11.A.6 conjunction-breaker) is that it needs no
forecast — only P&L accounting — and that the second rung does not automatically release. A book
that hits the flatten rung stays flat until a human writes down why it may resume; a mechanical
recovery in NAV must not silently re-arm the strategy. That freeze-until-reviewed behavior is the
behavioral countermeasure the study keeps returning to (the Druckenmiller-2000 / Amaranth lesson).

This module is the pure decision function. Applying the multiplier to target weights and logging
the freeze/clearance as override events belongs to the engine and the decision ledger.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

LadderRung = Literal["full", "halved", "flattened_frozen"]


class DrawdownLadder(BaseModel):
    """Book-level drawdown thresholds, as fractions of the high-water mark (0.08 == 8%)."""

    halve_at_pct: float
    flatten_at_pct: float

    @model_validator(mode="after")
    def _check_ordered(self) -> DrawdownLadder:
        if self.halve_at_pct <= 0 or self.flatten_at_pct <= 0:
            raise ValueError("ladder thresholds must be positive")
        if self.halve_at_pct >= self.flatten_at_pct:
            raise ValueError("halve threshold must be strictly below the flatten threshold")
        return self


class LadderState(BaseModel):
    """Persisted ladder state for one book. ``frozen`` survives a NAV recovery by design."""

    frozen: bool = False


class LadderAction(BaseModel):
    """The gross-exposure decision for one session."""

    # Multiply target gross exposure by this: 1.0 full, 0.5 halved, 0.0 flat.
    gross_multiplier: float
    rung: LadderRung
    frozen: bool
    detail: str


# Ranges straight from the Phase 15 L2 table. Numbers are hypotheses hardened per system at
# preregistration, never institutional facts — see the rulebook's own caveat.
LADDER_PRESETS = {
    "conservative": DrawdownLadder(halve_at_pct=0.06, flatten_at_pct=0.10),
    "moderate": DrawdownLadder(halve_at_pct=0.08, flatten_at_pct=0.12),
    "aggressive": DrawdownLadder(halve_at_pct=0.12, flatten_at_pct=0.18),
}


def apply_drawdown_ladder(
    *,
    drawdown_pct: float,
    state: LadderState,
    ladder: DrawdownLadder,
) -> LadderAction:
    """Decide gross exposure for a book given its drawdown from HWM and its persisted state.

    ``drawdown_pct`` is a non-negative fraction (0.09 == 9% below the high-water mark). A book
    already frozen stays flat regardless of drawdown — only an explicit written-review clearance
    (``clear_freeze``) releases it.
    """
    if drawdown_pct < 0:
        raise ValueError("drawdown_pct is a non-negative fraction from the high-water mark")

    if state.frozen:
        return LadderAction(
            gross_multiplier=0.0,
            rung="flattened_frozen",
            frozen=True,
            detail="Book is frozen pending written review; gross held at zero despite any recovery.",
        )
    if drawdown_pct >= ladder.flatten_at_pct:
        return LadderAction(
            gross_multiplier=0.0,
            rung="flattened_frozen",
            frozen=True,
            detail=(
                f"Drawdown {drawdown_pct:.1%} reached the flatten rung "
                f"({ladder.flatten_at_pct:.1%}); gross set to zero and book frozen for review."
            ),
        )
    if drawdown_pct >= ladder.halve_at_pct:
        return LadderAction(
            gross_multiplier=0.5,
            rung="halved",
            frozen=False,
            detail=(
                f"Drawdown {drawdown_pct:.1%} reached the halve rung "
                f"({ladder.halve_at_pct:.1%}); gross exposure halved."
            ),
        )
    return LadderAction(
        gross_multiplier=1.0,
        rung="full",
        frozen=False,
        detail="Drawdown within limits; full gross exposure permitted.",
    )


def clear_freeze(state: LadderState) -> LadderState:
    """Release a freeze after a written review. The caller must log the review as an override event.

    Returns a fresh un-frozen state; it does not itself re-arm exposure — the very next
    ``apply_drawdown_ladder`` call re-checks the live drawdown, so a book still below its flatten
    rung re-freezes immediately rather than trading through an unresolved loss.
    """
    return LadderState(frozen=False)
