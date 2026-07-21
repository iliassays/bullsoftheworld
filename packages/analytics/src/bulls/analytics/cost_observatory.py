"""Cost observatory: per-name trading-cost measurement for the Atlas validation protocol.

The institutional study (Phase 13.2 / Phase 14 Stage 0.3) forbids assumed trading costs. The
backtest engine today applies a single flat ``slippage_rate`` per market; the study is explicit
that this is not good enough — *half-spread measured per-name*, then the strategy stress-tested at
10/30/50 bps one-way, because "any system whose edge dies at 30 bps one-way in its actual universe
is dead," and in small caps the spread (not market impact) is retail's real cost.

We do not have bid/ask quote history for equities, only OHLC bars. The **Corwin-Schultz (2012)**
high-low estimator is built for exactly this: it recovers the effective proportional spread from
the ratio of daily high/low ranges across consecutive sessions, on the logic that the high-low
range reflects both true volatility (which scales with the interval) and the bid-ask bounce
(which does not). It is a *measurement from data*, not an assumption.

Known limitation, stated honestly per the study's evidence rules: the overnight-gap adjustment
from the paper's appendix is not applied here — only the standard negative-estimate-to-zero
flooring. On names with frequent large overnight gaps the estimate is biased high; the flooring
and the stress tiers are the guardrails. Refinement is a documented follow-up, not a silent gap.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel

# Corwin-Schultz normalizing constant 3 - 2*sqrt(2).
_CS_DENOM = 3.0 - 2.0 * math.sqrt(2.0)


class SpreadEstimate(BaseModel):
    """Effective proportional spread recovered from a name's high/low history."""

    code: str
    method: str = "corwin_schultz_high_low"
    # Number of valid consecutive-session pairs the estimate averaged over.
    observations: int
    # Full round-trip proportional spread S (a fraction, e.g. 0.004 = 40 bps).
    proportional_spread: float
    # One-way half-spread in basis points — the number the cost model consumes.
    half_spread_bps: float


class CostTier(BaseModel):
    """One one-way trading-cost scenario the backtest is required to survive."""

    label: str
    one_way_bps: float
    # True only for the tier derived from measured data; the rest are fixed stress floors.
    measured: bool = False


def corwin_schultz_spread(highs: Sequence[float], lows: Sequence[float]) -> float | None:
    """Estimate the effective proportional bid-ask spread from daily highs and lows.

    Returns the round-trip proportional spread S (a fraction), or ``None`` when there is not a
    single usable consecutive-session pair. Per-pair estimates that come out negative — pure
    estimation noise — are floored to zero before averaging, the standard Corwin-Schultz rule.
    """
    if len(highs) != len(lows):
        raise ValueError("highs and lows must be the same length")
    if len(highs) < 2:
        return None

    pair_spreads: list[float] = []
    for i in range(len(highs) - 1):
        h1, l1 = highs[i], lows[i]
        h2, l2 = highs[i + 1], lows[i + 1]
        # A session with a non-positive or inverted range carries no usable information.
        if h1 <= 0 or l1 <= 0 or h2 <= 0 or l2 <= 0 or h1 < l1 or h2 < l2:
            continue
        beta = math.log(h1 / l1) ** 2 + math.log(h2 / l2) ** 2
        window_high = max(h1, h2)
        window_low = min(l1, l2)
        gamma = math.log(window_high / window_low) ** 2
        alpha = (math.sqrt(2.0 * beta) - math.sqrt(beta)) / _CS_DENOM - math.sqrt(gamma / _CS_DENOM)
        spread = 2.0 * (math.exp(alpha) - 1.0) / (1.0 + math.exp(alpha))
        pair_spreads.append(max(spread, 0.0))

    if not pair_spreads:
        return None
    return sum(pair_spreads) / len(pair_spreads)


def estimate_spread(
    code: str,
    highs: Sequence[float],
    lows: Sequence[float],
    *,
    minimum_observations: int = 20,
) -> SpreadEstimate | None:
    """Per-name spread estimate. ``None`` if the history is too thin to measure honestly.

    ``minimum_observations`` guards against a spread quoted off a handful of sessions; the study
    would rather report "not measurable" than publish a number with no support (its omit-over-
    mislead rule).
    """
    spread = corwin_schultz_spread(highs, lows)
    if spread is None:
        return None
    # Count the same valid pairs the estimator used, so the support is reported honestly.
    valid_pairs = sum(
        1
        for i in range(len(highs) - 1)
        if highs[i] > 0
        and lows[i] > 0
        and highs[i + 1] > 0
        and lows[i + 1] > 0
        and highs[i] >= lows[i]
        and highs[i + 1] >= lows[i + 1]
    )
    if valid_pairs < minimum_observations:
        return None
    return SpreadEstimate(
        code=code,
        observations=valid_pairs,
        proportional_spread=spread,
        half_spread_bps=spread / 2.0 * 10_000.0,
    )


def cost_tiers(
    *,
    measured_half_spread_bps: float | None,
    fee_bps: float,
    stress_levels_bps: Sequence[float] = (10.0, 30.0, 50.0),
) -> list[CostTier]:
    """Assemble the one-way cost scenarios a backtest must be run against (Phase 13.2).

    The measured tier is half-spread + fees (omitted when the spread could not be measured); the
    stress tiers are fixed one-way floors the strategy's edge has to survive regardless of what
    the measurement said.
    """
    tiers: list[CostTier] = []
    if measured_half_spread_bps is not None:
        tiers.append(
            CostTier(
                label="measured",
                one_way_bps=round(measured_half_spread_bps + fee_bps, 4),
                measured=True,
            )
        )
    for level in stress_levels_bps:
        tiers.append(CostTier(label=f"stress_{level:g}bps", one_way_bps=float(level)))
    return tiers
