"""System C: the boring factor sleeve, and the nulls it must beat (Phase 12).

The four premia — value, momentum, quality, low-issuance — are the only return source in the
institutional study with 50+ years of evidence behind them. They also survive publication at only
about half their published magnitude (McLean-Pontiff), and nobody is *forced* to be on the other
side of them, so the study labels this book honestly: **beta-plus, not edge**.

That framing sets what this module is for. Phase 12 is blunt that System C's null — an index fund
— is "nearly unbeatable", and that the book exists to *measure whether any active implementation
of ours beats the null*, not to assume it does. So the nulls are built here alongside the sleeve
itself, because Phase 13.3.4 requires them run in the same harness: a cap-weighted index, 1/N over
the same universe, and a naive single-factor version. Beating only a strawman is a null result.

**Point-in-time is the whole ballgame for a fundamentals strategy.** Two rules, both enforced here:

1. A fact may only be used once it was *published* — filtered on ``filed_at``, never period end.
   A December quarter is not knowable in January.
2. When a period has been restated, the **first disclosure** is used, not the latest value. Our own
   data shows 1,798 period-metrics carrying multiple filings; ranking on restated figures would
   score the strategy on numbers nobody had at the time. This is Phase 13.1.4's restatement
   quarantine applied to ourselves.

Ranks, not z-scores: fundamental ratios have fat tails and a single outlier can dominate a
z-scored composite. Cross-sectional percentile ranks are the robust standard.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, Field

# Momentum skips the most recent month: the classic 12-1 construction, which avoids the
# well-documented short-term reversal that contaminates a raw 12-month return.
MOMENTUM_LOOKBACK_SESSIONS = 252
MOMENTUM_SKIP_SESSIONS = 21

FACTOR_NAMES = ("value", "quality", "momentum", "low_issuance")


class FundamentalFact(BaseModel):
    """One reported figure, carrying both the period it describes and when it became public."""

    code: str
    metric: str
    value: float
    period_end: dt.date
    filed_at: dt.date


class PricePoint(BaseModel):
    date: dt.date
    close: float = Field(gt=0)


class SecurityFactorInputs(BaseModel):
    """Everything needed to score one security, already resolved point-in-time."""

    code: str
    prices: list[PricePoint]
    # Point-in-time fundamentals as of the signal date, and as of a year earlier (for issuance).
    fundamentals: dict[str, float] = Field(default_factory=dict)
    prior_fundamentals: dict[str, float] = Field(default_factory=dict)


class FactorScores(BaseModel):
    """Raw factor values for one security. ``None`` means not computable, never zero."""

    code: str
    value: float | None = None
    quality: float | None = None
    momentum: float | None = None
    low_issuance: float | None = None
    volatility: float | None = None

    def available(self) -> int:
        return sum(1 for name in FACTOR_NAMES if getattr(self, name) is not None)


class RankedSecurity(BaseModel):
    """A security's composite standing. Higher composite is more attractive."""

    code: str
    composite: float
    percentile_ranks: dict[str, float]
    factors_available: int
    volatility: float | None = None


class SleevePolicy(BaseModel):
    """Construction limits. Phase 12: ~30-50 names, 3% cap, vol-scaled within 1/N bands."""

    target_positions: int = Field(default=40, ge=5)
    max_position_pct: float = Field(default=0.03, gt=0, le=0.10)
    # Vol scaling is bounded so it tilts the book without concentrating it (Phase 5's 1/N bands).
    weight_band_low: float = Field(default=0.5, gt=0, le=1.0)
    weight_band_high: float = Field(default=1.5, ge=1.0)
    # A security must have at least this many of the four factors to be ranked at all.
    minimum_factors: int = Field(default=3, ge=1, le=4)


def point_in_time_fundamentals(
    facts: Iterable[FundamentalFact], *, as_of: dt.date
) -> dict[str, dict[str, float]]:
    """Resolve each security's fundamentals as they were knowable on ``as_of``.

    Only facts already filed by ``as_of`` are eligible. Among those, the most recent *period* wins;
    where a period was filed more than once, the **earliest** filing wins, so a later restatement
    never leaks backwards into a historical signal.
    """
    # (code, metric) -> (period_end, filed_at, value)
    best: dict[tuple[str, str], tuple[dt.date, dt.date, float]] = {}
    for fact in facts:
        if fact.filed_at > as_of:
            continue
        key = (fact.code, fact.metric)
        current = best.get(key)
        if current is None:
            best[key] = (fact.period_end, fact.filed_at, fact.value)
            continue
        period, filed, _ = current
        if fact.period_end > period or (
            fact.period_end == period and fact.filed_at < filed
        ):
            best[key] = (fact.period_end, fact.filed_at, fact.value)

    resolved: dict[str, dict[str, float]] = {}
    for (code, metric), (_, _, value) in best.items():
        resolved.setdefault(code, {})[metric] = value
    return resolved


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _annualized_volatility(prices: Sequence[PricePoint], lookback: int = 120) -> float | None:
    closes = [point.close for point in prices][-(lookback + 1) :]
    if len(closes) < 21:
        return None
    returns = [
        closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1] > 0
    ]
    if len(returns) < 20:
        return None
    deviation = statistics.stdev(returns)
    return deviation * (252**0.5) if deviation > 0 else None


def _momentum_12_1(prices: Sequence[PricePoint]) -> float | None:
    closes = [point.close for point in prices]
    if len(closes) < MOMENTUM_LOOKBACK_SESSIONS + 1:
        return None
    recent = closes[-(MOMENTUM_SKIP_SESSIONS + 1)]
    old = closes[-(MOMENTUM_LOOKBACK_SESSIONS + 1)]
    if old <= 0:
        return None
    return recent / old - 1.0


def compute_factor_scores(inputs: SecurityFactorInputs) -> FactorScores:
    """Score one security on the four premia. Missing inputs yield ``None``, never a zero."""
    facts = inputs.fundamentals
    prior = inputs.prior_fundamentals
    latest_close = inputs.prices[-1].close if inputs.prices else None
    shares = facts.get("shares_outstanding")
    market_cap = latest_close * shares if latest_close and shares else None

    # Value: book-to-price. Negative equity is a distress signal, not a bargain — excluded.
    equity = facts.get("equity")
    book_to_price = None
    if equity is not None and equity > 0:
        book_to_price = _safe_ratio(equity, market_cap)

    # Quality: return on equity, on the same positive-equity condition.
    quality = None
    if equity is not None and equity > 0:
        quality = _safe_ratio(facts.get("net_income"), equity)

    # Low issuance: shrinking share count scores high, dilution scores low.
    low_issuance = None
    prior_shares = prior.get("shares_outstanding")
    if shares is not None and prior_shares is not None and prior_shares > 0:
        low_issuance = -(shares / prior_shares - 1.0)

    return FactorScores(
        code=inputs.code,
        value=book_to_price,
        quality=quality,
        momentum=_momentum_12_1(inputs.prices),
        low_issuance=low_issuance,
        volatility=_annualized_volatility(inputs.prices),
    )


def _percentile_ranks(values: dict[str, float]) -> dict[str, float]:
    """Cross-sectional percentile rank in [0, 1]; ties share the average rank."""
    if not values:
        return {}
    ordered = sorted(values.items(), key=lambda pair: pair[1])
    ranks: dict[str, float] = {}
    n = len(ordered)
    index = 0
    while index < n:
        stop = index
        while stop + 1 < n and ordered[stop + 1][1] == ordered[index][1]:
            stop += 1
        average_position = (index + stop) / 2.0
        percentile = average_position / (n - 1) if n > 1 else 0.5
        for offset in range(index, stop + 1):
            ranks[ordered[offset][0]] = percentile
        index = stop + 1
    return ranks


def rank_universe(
    scores: Iterable[FactorScores], policy: SleevePolicy | None = None
) -> list[RankedSecurity]:
    """Rank the universe on the equally-weighted composite of available factors.

    A security is ranked on whichever factors it has, provided it clears ``minimum_factors`` — a
    name missing one input is diluted rather than discarded, but a name missing most of them is
    not ranked at all, because a composite built from one factor is not the strategy.
    """
    policy = policy or SleevePolicy()
    all_scores = list(scores)
    eligible = [s for s in all_scores if s.available() >= policy.minimum_factors]
    if not eligible:
        return []

    per_factor: dict[str, dict[str, float]] = {}
    for name in FACTOR_NAMES:
        values = {
            score.code: getattr(score, name)
            for score in eligible
            if getattr(score, name) is not None
        }
        per_factor[name] = _percentile_ranks(values)

    ranked: list[RankedSecurity] = []
    for score in eligible:
        ranks = {
            name: per_factor[name][score.code]
            for name in FACTOR_NAMES
            if score.code in per_factor[name]
        }
        if not ranks:
            continue
        ranked.append(
            RankedSecurity(
                code=score.code,
                composite=sum(ranks.values()) / len(ranks),
                percentile_ranks=ranks,
                factors_available=score.available(),
                volatility=score.volatility,
            )
        )
    ranked.sort(key=lambda item: (-item.composite, item.code))
    return ranked


def sleeve_weights(
    ranked: Sequence[RankedSecurity], policy: SleevePolicy | None = None
) -> dict[str, float]:
    """Build the sleeve: top names, inverse-vol scaled inside 1/N bands, per-name capped.

    Phase 5's two most evidence-backed construction rules combined — 1/N as the anchor (no
    optimizer beat it out of sample) and volatility scaling as a bounded tilt. The bands stop the
    vol tilt from quietly turning an equal-weight book into a concentrated one.
    """
    policy = policy or SleevePolicy()
    selected = list(ranked[: policy.target_positions])
    if not selected:
        return {}

    equal = 1.0 / len(selected)
    floor = equal * policy.weight_band_low
    ceiling = min(equal * policy.weight_band_high, policy.max_position_pct)
    if ceiling < floor:
        # A tight per-name cap outranks the band: respect the cap.
        floor = ceiling

    raw: dict[str, float] = {}
    for item in selected:
        # Unknown volatility falls back to equal weight rather than being excluded or guessed at.
        raw[item.code] = 1.0 / item.volatility if item.volatility else equal
    total = sum(raw.values())
    if total <= 0:
        return {code: round(min(equal, policy.max_position_pct), 6) for code in raw}

    weights = {code: value / total for code, value in raw.items()}
    clamped = {code: min(max(weight, floor), ceiling) for code, weight in weights.items()}
    # Renormalize only if the book would otherwise exceed fully invested; leaving it under is fine
    # (cash is a valid state) but leverage is not.
    gross = sum(clamped.values())
    if gross > 1.0:
        clamped = {code: weight / gross for code, weight in clamped.items()}
    return {code: round(weight, 6) for code, weight in clamped.items()}


def equal_weight_null(codes: Sequence[str]) -> dict[str, float]:
    """The 1/N null (DeMiguel). System C must beat this or it is not earning its complexity."""
    if not codes:
        return {}
    weight = 1.0 / len(codes)
    return {code: round(weight, 6) for code in codes}


def single_factor_null(
    scores: Iterable[FactorScores], factor: str, policy: SleevePolicy | None = None
) -> dict[str, float]:
    """A naive one-factor version of the sleeve — Phase 13.3.4's anti-strawman requirement.

    If the four-factor composite cannot beat plain momentum (or plain value), the composite is
    decoration and should be reported as such.
    """
    if factor not in FACTOR_NAMES:
        raise ValueError(f"unknown factor {factor!r}")
    policy = policy or SleevePolicy()
    values = {
        score.code: getattr(score, factor)
        for score in scores
        if getattr(score, factor) is not None
    }
    if not values:
        return {}
    ranks = _percentile_ranks(values)
    ordered = sorted(ranks.items(), key=lambda pair: (-pair[1], pair[0]))
    chosen = [code for code, _ in ordered[: policy.target_positions]]
    return equal_weight_null(chosen)
