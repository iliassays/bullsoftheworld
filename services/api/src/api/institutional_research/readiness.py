"""Point-in-time data admission status for registered but blocked Atlas hypotheses."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.schemas import (
    IntradaySessionQualityOut,
    StrategyDataReadinessOut,
)
from bulls.core.models import (
    IntradayBar,
    IntradayCaptureSession,
    IntradayQuoteObservation,
    ResearchWorkspace,
)
from bulls.market_data.calendar import most_recent_completed_session

MINIMUM_COMPLETE_INTRADAY_SESSIONS = 60


async def load_trend_pullback_data_readiness(
    session: AsyncSession,
    *,
    workspace: ResearchWorkspace,
    now: dt.datetime | None = None,
) -> StrategyDataReadinessOut:
    if workspace.market != "DSE":
        raise ValueError("The DSE trend-pullback data contract is unavailable for this market")
    current = now or dt.datetime.now(dt.UTC)
    latest = await session.scalar(
        select(IntradayCaptureSession)
        .where(IntradayCaptureSession.market == workspace.market)
        .order_by(IntradayCaptureSession.session_date.desc())
        .limit(1)
    )
    session_count, complete_count, eligible_count, first_date, last_date = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(IntradayCaptureSession.status == "complete"),
                func.count().filter(IntradayCaptureSession.research_eligible.is_(True)),
                func.min(IntradayCaptureSession.session_date),
                func.max(IntradayCaptureSession.session_date),
            ).where(IntradayCaptureSession.market == workspace.market)
        )
    ).one()
    observation_count = int(
        await session.scalar(
            select(func.count())
            .select_from(IntradayQuoteObservation)
            .where(IntradayQuoteObservation.market == workspace.market)
        )
        or 0
    )
    bar_count = int(
        await session.scalar(
            select(func.count())
            .select_from(IntradayBar)
            .where(IntradayBar.market == workspace.market)
        )
        or 0
    )
    completed_sessions = int(complete_count or 0)
    blockers: list[str] = []
    if completed_sessions < MINIMUM_COMPLETE_INTRADAY_SESSIONS:
        blockers.append(
            f"Only {completed_sessions} complete intraday sessions are retained; "
            f"the preregistration floor is {MINIMUM_COMPLETE_INTRADAY_SESSIONS}."
        )
    expected_latest = most_recent_completed_session(current, market="DSE")
    if last_date is None or last_date < expected_latest:
        blockers.append(
            f"The latest completed DSE session ({expected_latest.isoformat()}) has no capture audit."
        )
    if latest is not None and not latest.research_eligible:
        blockers.extend(str(item) for item in latest.blockers)
    blockers.extend(
        [
            "Inactive and delisted DSE history is not yet complete.",
            "Effective-dated DSE circuit and trading-constraint history is not yet complete.",
            "The intraday trend-pullback experiment specification has not been frozen.",
        ]
    )
    blockers = list(dict.fromkeys(blockers))
    latest_quality = None
    if latest is not None:
        age_minutes = (
            max(
                0.0,
                (current - latest.latest_observed_at).total_seconds() / 60,
            )
            if latest.latest_observed_at is not None
            else None
        )
        latest_quality = IntradaySessionQualityOut(
            session_date=latest.session_date,
            status=latest.status,
            observed_slots=latest.observed_slot_count,
            expected_slots=latest.expected_slot_count,
            observed_symbols=latest.observed_symbol_count,
            expected_symbols=latest.expected_symbol_count,
            slot_completeness_pct=float(latest.slot_completeness_pct),
            symbol_completeness_pct=float(latest.symbol_completeness_pct),
            vwap_coverage_pct=float(latest.vwap_coverage_pct),
            counter_regressions=latest.counter_regression_count,
            latest_observed_at=latest.latest_observed_at,
            capture_age_minutes=round(age_minutes, 2) if age_minutes is not None else None,
            research_eligible=latest.research_eligible,
            blockers=[str(item) for item in latest.blockers],
        )
    return StrategyDataReadinessOut(
        workspace_id=workspace.id,
        tenant_id=workspace.tenant_id,
        market="DSE",
        strategy_key="dse_trend_pullback_intraday_v1",
        state="data_blocked",
        bar_kind="sampled_delayed_quote",
        time_quality="ingestion_upper_bound",
        captured_sessions=int(session_count or 0),
        complete_sessions=completed_sessions,
        eligible_capture_sessions=int(eligible_count or 0),
        required_complete_sessions=MINIMUM_COMPLETE_INTRADAY_SESSIONS,
        observation_count=observation_count,
        bar_count=bar_count,
        first_session=first_date,
        latest_session=last_date,
        historical_diagnostic_eligible=False,
        blockers=blockers,
        latest_quality=latest_quality,
    )
