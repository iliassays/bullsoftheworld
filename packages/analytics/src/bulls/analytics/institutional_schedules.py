"""Shared point-in-time schedule construction for Atlas institutional systems."""

from __future__ import annotations

import bisect
import datetime as dt
from dataclasses import dataclass
from typing import Any

from bulls.analytics.cost_observatory import estimate_spread
from bulls.analytics.factor_sleeve import (
    FundamentalObservation,
    PricePoint,
    SecurityFactorInputs,
    SleevePolicy,
    compute_factor_scores,
    equal_weight_null,
    point_in_time_factor_fundamentals,
    rank_universe,
    select_with_turnover_buffer,
    single_factor_null,
    sleeve_weights,
)
from bulls.analytics.research_strategy import StrategyBar


@dataclass(frozen=True)
class FactorScheduleBundle:
    strategy: dict[dt.date, dict[str, float]]
    equal_weight_null: dict[dt.date, dict[str, float]]
    momentum_null: dict[dt.date, dict[str, float]]
    cap_weighted_null: dict[dt.date, dict[str, float]]
    diagnostics: dict[str, Any]


def _cap_weighted_null(
    codes: list[str],
    *,
    closes: dict[str, float],
    fundamentals: dict[str, dict[str, float]],
) -> dict[str, float]:
    market_caps = {
        code: closes[code] * fundamentals[code]["shares_outstanding"]
        for code in codes
        if code in closes
        and fundamentals.get(code, {}).get("shares_outstanding", 0) > 0
    }
    gross = sum(market_caps.values())
    if gross <= 0:
        return {}
    return {code: round(value / gross, 8) for code, value in market_caps.items()}


def build_factor_schedules(
    *,
    bars: dict[str, list[StrategyBar]],
    observations: list[FundamentalObservation],
    sessions: list[dt.date],
    policy: SleevePolicy,
    max_half_spread_bps: float,
    rebalance_sessions: int = 21,
) -> FactorScheduleBundle:
    """Build System C and its nulls from data knowable at each monthly rebalance."""

    strategy: dict[dt.date, dict[str, float]] = {}
    equal_weight: dict[dt.date, dict[str, float]] = {}
    momentum: dict[dt.date, dict[str, float]] = {}
    cap_weighted: dict[dt.date, dict[str, float]] = {}
    holdings: set[str] = set()
    ranked_counts: list[int] = []
    selected_counts: list[int] = []
    spread_measurements: list[float] = []
    rejected_by_spread = 0
    prepared = {
        code: (
            [bar.date for bar in history],
            [PricePoint(date=bar.date, close=bar.close) for bar in history],
        )
        for code, history in bars.items()
    }

    for index, as_of in enumerate(sessions):
        if index < 252 or index % rebalance_sessions != 0:
            continue
        current = point_in_time_factor_fundamentals(observations, as_of=as_of)
        prior = point_in_time_factor_fundamentals(
            observations, as_of=as_of - dt.timedelta(days=365)
        )
        scores = []
        closes: dict[str, float] = {}
        for code, (dates, points) in prepared.items():
            cut = bisect.bisect_right(dates, as_of)
            if cut < 253:
                continue
            completed = bars[code][max(0, cut - 60) : cut]
            spread = estimate_spread(
                code,
                [bar.high for bar in completed],
                [bar.low for bar in completed],
            )
            if spread is None or spread.half_spread_bps > max_half_spread_bps:
                rejected_by_spread += 1
                continue
            spread_measurements.append(spread.half_spread_bps)
            closes[code] = points[cut - 1].close
            scores.append(
                compute_factor_scores(
                    SecurityFactorInputs(
                        code=code,
                        prices=points[:cut],
                        fundamentals=current.get(code, {}),
                        prior_fundamentals=prior.get(code, {}),
                    )
                )
            )
        ranked = rank_universe(scores, policy)
        if not ranked:
            continue
        selected = select_with_turnover_buffer(
            ranked,
            current_holdings=sorted(holdings),
            policy=policy,
        )
        weights = sleeve_weights(selected, policy)
        holdings = set(weights)
        eligible_codes = [item.code for item in ranked]
        strategy[as_of] = weights
        equal_weight[as_of] = equal_weight_null(eligible_codes)
        momentum[as_of] = single_factor_null(scores, "momentum", policy)
        cap_weighted[as_of] = _cap_weighted_null(
            eligible_codes,
            closes=closes,
            fundamentals=current,
        )
        ranked_counts.append(len(ranked))
        selected_counts.append(len(weights))

    diagnostics = {
        "rebalances": len(strategy),
        "average_ranked": (
            round(sum(ranked_counts) / len(ranked_counts), 1) if ranked_counts else 0.0
        ),
        "average_selected": (
            round(sum(selected_counts) / len(selected_counts), 1)
            if selected_counts
            else 0.0
        ),
        "spread_observations": len(spread_measurements),
        "rejected_by_spread": rejected_by_spread,
        "median_half_spread_bps": (
            round(sorted(spread_measurements)[len(spread_measurements) // 2], 2)
            if spread_measurements
            else None
        ),
    }
    return FactorScheduleBundle(
        strategy=strategy,
        equal_weight_null=equal_weight,
        momentum_null=momentum,
        cap_weighted_null=cap_weighted,
        diagnostics=diagnostics,
    )
