"""DSE-only database adapter for the locked compression-breakout experiment."""

from __future__ import annotations

import bisect
import datetime as dt
import statistics
from collections import Counter, defaultdict
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.institutional_backtests import (
    InstitutionalBacktestPreparation,
)
from api.institutional_research.schemas import BacktestRequest
from bulls.analytics.adjustments import adjustment_factor
from bulls.analytics.dse_compression_breakout import (
    SOURCE_FAMILY,
    SOURCE_METHODOLOGY_VERSION,
    CompressionBreakoutObservation,
    CompressionBreakoutPolicy,
    build_compression_breakout_schedule,
    delay_weight_schedule,
)
from bulls.analytics.dse_selective_compression import (
    SelectiveCompressionObservation,
    SelectiveCompressionPolicy,
    build_selective_compression_schedule,
    build_selective_features,
)
from bulls.analytics.research_strategy import StrategyBar, StrategySecurity
from bulls.core.models import DailyBar, MarketSummary, SqueezeDailyState, Symbol
from bulls.core.symbol_lifecycle import PRIVATE_RESEARCH_STATUSES


def _trailing_average_daily_value_mn(
    daily_values: list[tuple[dt.date, float]],
    *,
    as_of: dt.date,
    sessions: int = 20,
) -> float | None:
    """Average completed-session traded value through ``as_of`` with no future observations."""

    if sessions < 1:
        raise ValueError("sessions must be positive")
    index = bisect.bisect_right([date for date, _value in daily_values], as_of)
    completed = daily_values[max(0, index - sessions) : index]
    if len(completed) < sessions:
        return None
    return statistics.fmean(value for _date, value in completed) / 1_000_000


async def prepare_dse_compression_backtest(
    session: AsyncSession,
    *,
    request: BacktestRequest,
    evidence_mode: Literal["forward", "reconstructed"] | None = None,
    signal_not_before: dt.date | None = None,
) -> InstitutionalBacktestPreparation:
    """Load a market-bound archive and build the frozen 20-session target schedule.

    ``evidence_mode=None`` is the historical diagnostic. A live shadow reconciliation must pass
    ``"forward"`` plus its registration-date floor.
    """

    end = request.end_date or await session.scalar(
        select(func.max(DailyBar.date)).where(DailyBar.market == "DSE")
    )
    if end is None:
        return InstitutionalBacktestPreparation(
            securities=[],
            weight_schedule={},
            execution_timing="next_open",
            failed_gates=["No completed DSE daily-bar history is available."],
        )
    start = request.start_date or end - dt.timedelta(days=365 * 3 + 30)
    if start >= end:
        raise ValueError("start_date must be earlier than end_date")

    conditions = [
        SqueezeDailyState.market == "DSE",
        SqueezeDailyState.family == SOURCE_FAMILY,
        SqueezeDailyState.methodology_version == SOURCE_METHODOLOGY_VERSION,
        # Forming/watch/none rows never change either portfolio schedule. Excluding them keeps
        # multi-year diagnostics bounded without changing confirmation or terminal semantics.
        SqueezeDailyState.state.in_(("confirmed", "failed", "exhausted")),
        SqueezeDailyState.as_of_date >= start,
        SqueezeDailyState.as_of_date <= end,
    ]
    if request.codes:
        conditions.append(SqueezeDailyState.code.in_({code.upper() for code in request.codes}))
    rows = list(
        await session.scalars(
            select(SqueezeDailyState)
            .where(*conditions)
            .order_by(SqueezeDailyState.as_of_date, SqueezeDailyState.code)
        )
    )
    observations = [
        CompressionBreakoutObservation(
            code=row.code,
            as_of_date=row.as_of_date,
            state=row.state,
            previous_state=row.previous_state,
            evidence_mode=row.evidence_mode,
            methodology_version=row.methodology_version,
            setup_price=row.setup_price,
            trigger_price=row.trigger_price,
            invalidation_price=row.invalidation_price,
            risk_per_share=row.risk_per_share,
            average_daily_value_mn=row.average_dollar_volume_mn,
        )
        for row in rows
    ]

    symbol_conditions = [
        Symbol.market == "DSE",
        Symbol.is_active.is_(True),
        Symbol.is_hidden.is_(False),
        Symbol.research_status.in_(PRIVATE_RESEARCH_STATUSES),
    ]
    if request.codes:
        symbol_conditions.append(Symbol.code.in_({code.upper() for code in request.codes}))
    symbols = {
        row.code: row
        for row in await session.scalars(
            select(Symbol).where(*symbol_conditions).order_by(Symbol.code)
        )
    }
    # The registered rule is an all-eligible-DSE scan. A small interactive universe cap would
    # silently omit future confirmations, so it is recorded as a diagnostic request limitation
    # rather than allowed to redefine the strategy.
    failed_gates: list[str] = [
        "Inactive and delisted DSE security history is incomplete; reconstructed results have survivorship bias.",
        "The DSE corporate-action adjustment audit is incomplete for the evaluation window.",
        "Historical squeeze states reconstructed from current survivors are diagnostic and cannot authorize promotion.",
    ]
    if request.codes:
        failed_gates.append(
            "A user-selected ticker subset is diagnostic and cannot establish cross-sectional evidence."
        )
    elif request.universe_limit < len(symbols):
        failed_gates.append(
            "The requested universe cap is ignored because the preregistered strategy scans every eligible DSE security."
        )

    # Selective features require 64 completed sessions before the first evaluated signal.
    # Calendar days are intentionally generous because DSE holidays make 90 days insufficient.
    bar_start = start - dt.timedelta(days=140)
    bars = list(
        await session.scalars(
            select(DailyBar)
            .where(
                DailyBar.market == "DSE",
                DailyBar.code.in_(list(symbols)),
                DailyBar.date >= bar_start,
                DailyBar.date <= end,
            )
            .order_by(DailyBar.code, DailyBar.date)
        )
    )
    grouped: dict[str, list[StrategyBar]] = defaultdict(list)
    observed_daily_values: dict[str, list[tuple[dt.date, float]]] = defaultdict(list)
    corrupt_codes: set[str] = set()
    adjusted_rows = 0
    for row in bars:
        if min(row.open or 0, row.high or 0, row.low or 0, row.close or 0) <= 0:
            corrupt_codes.add(row.code)
            continue
        factor = adjustment_factor(float(row.close), row.adjusted_close)
        if factor is None:
            corrupt_codes.add(row.code)
            continue
        if row.adjusted_close is not None:
            adjusted_rows += 1
        observed_daily_values[row.code].append((row.date, float(row.close) * int(row.volume or 0)))
        grouped[row.code].append(
            StrategyBar(
                date=row.date,
                open=float(row.open) * factor,
                high=float(row.high) * factor,
                low=float(row.low) * factor,
                close=float(row.close) * factor,
                volume=int(row.volume or 0),
            )
        )
    for code in corrupt_codes:
        grouped.pop(code, None)
        observed_daily_values.pop(code, None)
    enriched_observations: list[CompressionBreakoutObservation] = []
    computed_adv_observations = 0
    unresolved_adv_observations = 0
    for observation in observations:
        computed = _trailing_average_daily_value_mn(
            observed_daily_values.get(observation.code, []),
            as_of=observation.as_of_date,
        )
        if computed is not None:
            computed_adv_observations += 1
        elif observation.average_daily_value_mn is None:
            unresolved_adv_observations += 1
        enriched_observations.append(
            observation.model_copy(
                update={
                    "average_daily_value_mn": (
                        computed if computed is not None else observation.average_daily_value_mn
                    )
                }
            )
        )
    observations = enriched_observations
    selective_strategy = request.strategy_key == "dse_selective_compression_v1"
    benchmark_closes: list[tuple[dt.date, float]] = []
    selective_observations: list[SelectiveCompressionObservation] = []
    feature_observations = 0
    if selective_strategy:
        benchmark_closes = [
            (row.date, float(row.dsex))
            for row in (
                await session.execute(
                    select(MarketSummary.date, MarketSummary.dsex)
                    .where(
                        MarketSummary.market == "DSE",
                        MarketSummary.date >= bar_start,
                        MarketSummary.date <= end,
                        MarketSummary.dsex.is_not(None),
                    )
                    .order_by(MarketSummary.date)
                )
            ).all()
            if row.dsex is not None and row.dsex > 0
        ]
        for observation in observations:
            features = (
                build_selective_features(
                    bars=grouped.get(observation.code, []),
                    benchmark_closes=benchmark_closes,
                    as_of=observation.as_of_date,
                    trigger_price=observation.trigger_price,
                    invalidation_price=observation.invalidation_price,
                )
                if observation.state == "confirmed" and observation.previous_state != "confirmed"
                else None
            )
            if features is not None:
                feature_observations += 1
            selective_observations.append(
                SelectiveCompressionObservation(
                    **observation.model_dump(),
                    features=features,
                )
            )
    securities = [
        StrategySecurity(
            code=code,
            sector=symbols[code].sector or "Unclassified",
            cap_tier="unclassified",
            bars=history,
        )
        for code, history in sorted(grouped.items())
        if history
    ]
    sessions = sorted({bar.date for security in securities for bar in security.bars})
    if selective_strategy:
        policy = SelectiveCompressionPolicy()
        built = build_selective_compression_schedule(
            observations=selective_observations,
            sessions=sessions,
            policy=policy,
            evidence_mode=evidence_mode,
            signal_not_before=signal_not_before,
        )
        liquidity_baseline = build_compression_breakout_schedule(
            observations=observations,
            sessions=sessions,
            policy=CompressionBreakoutPolicy(
                holding_sessions=policy.holding_sessions,
                maximum_positions=policy.maximum_positions,
                maximum_gross_weight=policy.maximum_gross_weight,
                maximum_position_weight=policy.maximum_position_weight,
                risk_budget_per_position=policy.risk_budget_per_position,
                minimum_position_weight=policy.minimum_position_weight,
                minimum_average_daily_value_mn=policy.minimum_average_daily_value_mn,
                maximum_stop_distance_pct=policy.maximum_stop_distance_pct,
            ),
            evidence_mode=evidence_mode,
            signal_not_before=signal_not_before,
        )
    else:
        policy = CompressionBreakoutPolicy()
        built = build_compression_breakout_schedule(
            observations=observations,
            sessions=sessions,
            policy=policy,
            evidence_mode=evidence_mode,
            signal_not_before=signal_not_before,
        )
        liquidity_baseline = None
    if not built.target_weights:
        failed_gates.append(
            "No confirmation passed the registered liquidity, risk-geometry, and portfolio-capacity gates."
        )
    rejection_counts = Counter(item.reason for item in built.rejections)
    evidence_counts = Counter(row.evidence_mode for row in observations)
    observation_dates = sorted({row.as_of_date for row in observations})
    placebo = delay_weight_schedule(
        built.target_weights,
        sessions=sessions,
        delay_sessions=5,
    )
    if built.target_weights and not placebo:
        failed_gates.append(
            "The five-session timing placebo has no executable delayed target changes."
        )
    comparators = {
        "confirmation_timing_plus_5_sessions": placebo,
    }
    if liquidity_baseline is not None:
        comparators["liquidity_only_three_slot_baseline"] = liquidity_baseline.target_weights
    return InstitutionalBacktestPreparation(
        securities=securities,
        weight_schedule=built.target_weights,
        execution_timing="next_open",
        comparators=comparators,
        diagnostics={
            "source_family": SOURCE_FAMILY,
            "source_methodology": SOURCE_METHODOLOGY_VERSION,
            "evidence_filter": evidence_mode or "historical_diagnostic_all",
            "signal_not_before": signal_not_before.isoformat() if signal_not_before else None,
            "observations": len(observations),
            "first_observation_date": (
                observation_dates[0].isoformat() if observation_dates else None
            ),
            "last_observation_date": (
                observation_dates[-1].isoformat() if observation_dates else None
            ),
            "observation_sessions": len(observation_dates),
            "evidence_counts": dict(evidence_counts),
            "confirmations": built.confirmations,
            "quality_qualified": getattr(built, "quality_qualified", None),
            "accepted_entries": built.accepted_entries,
            "exits": built.exits,
            "rejections": dict(rejection_counts),
            "policy": policy.model_dump(mode="json"),
            "adjusted_bar_rows": adjusted_rows,
            "total_bar_rows": len(bars),
            "liquidity_measure": "trailing_20_completed_sessions_close_times_volume",
            "computed_liquidity_observations": computed_adv_observations,
            "unresolved_liquidity_observations": unresolved_adv_observations,
            "selective_feature_observations": feature_observations,
            "benchmark_feature_observations": len(benchmark_closes),
            "eligible_security_count": len(securities),
        },
        failed_gates=failed_gates,
        inactive_security_history_complete=False,
        point_in_time_inputs_complete=evidence_mode == "forward",
    )
