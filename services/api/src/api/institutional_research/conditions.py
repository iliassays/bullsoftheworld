"""Tenant-safe Atlas condition scanner and explicit alert subscriptions."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import and_, case, desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.institutional_research.schemas import (
    DossierConditionCheckOut,
    ResearchConditionCalibrationOut,
    ResearchConditionDefinitionOut,
    ResearchConditionScanItemOut,
    ResearchConditionScanOut,
    ResearchConditionSubscriptionOut,
)
from bulls.analytics import CONDITION_REGISTRY, METHODOLOGY_VERSION
from bulls.core.models import (
    ResearchConditionCalibration,
    ResearchConditionSubscription,
    ResearchConditionTransition,
    Symbol,
    TickerAnalytics,
)
from bulls.core.symbol_lifecycle import PRIVATE_RESEARCH_STATUSES

_CONDITIONS = {condition.key: condition for condition in CONDITION_REGISTRY}


def _definition(condition_key: str) -> ResearchConditionDefinitionOut:
    condition = _CONDITIONS.get(condition_key)
    if condition is None:
        raise ValueError("Unknown research condition")
    return ResearchConditionDefinitionOut(
        key=condition.key,
        version=condition.version,
        title=condition.title,
        category=condition.category,
        why_it_matters=condition.why_it_matters,
        limitation=condition.limitation,
    )


def _latest_transition_subquery(market: str, condition_key: str, condition_version: str):
    return (
        select(
            ResearchConditionTransition.code.label("code"),
            ResearchConditionTransition.as_of_date.label("observed_on"),
            ResearchConditionTransition.reference_close.label("reference_close"),
            ResearchConditionTransition.checks.label("checks"),
            ResearchConditionTransition.evidence_mode.label("evidence_mode"),
            ResearchConditionTransition.state.label("state"),
            func.row_number()
            .over(
                partition_by=ResearchConditionTransition.code,
                order_by=ResearchConditionTransition.as_of_date.desc(),
            )
            .label("row_number"),
        )
        .where(
            ResearchConditionTransition.market == market,
            ResearchConditionTransition.condition_key == condition_key,
            ResearchConditionTransition.condition_version == condition_version,
            ResearchConditionTransition.methodology_version == METHODOLOGY_VERSION,
        )
        .subquery("latest_condition_transitions")
    )


def _cap_filter(cap_tier: str | None):
    if cap_tier == "unclassified":
        return TickerAnalytics.cap_tier.is_(None)
    if cap_tier is not None:
        return TickerAnalytics.cap_tier == cap_tier
    return None


async def load_condition_scan(
    session: AsyncSession,
    *,
    tenant_id: str,
    market: str,
    workspace_id: uuid.UUID,
    user_id: int,
    condition_key: str,
    cap_tier: str | None,
    new_only: bool,
    limit: int,
) -> ResearchConditionScanOut:
    definition = _definition(condition_key)
    latest_session_date = await session.scalar(
        select(func.max(TickerAnalytics.as_of_date)).where(TickerAnalytics.market == market)
    )
    latest = _latest_transition_subquery(market, condition_key, definition.version)
    is_new = and_(
        latest.c.evidence_mode == "forward",
        latest.c.observed_on == latest_session_date,
    )
    subscription_join = and_(
        ResearchConditionSubscription.tenant_id == tenant_id,
        ResearchConditionSubscription.user_id == user_id,
        ResearchConditionSubscription.market == market,
        ResearchConditionSubscription.code == latest.c.code,
        ResearchConditionSubscription.condition_key == condition_key,
        ResearchConditionSubscription.condition_version == definition.version,
        ResearchConditionSubscription.methodology_version == METHODOLOGY_VERSION,
    )
    base_conditions = [
        latest.c.row_number == 1,
        latest.c.state == "observed",
        Symbol.market == market,
        Symbol.is_active.is_(True),
        Symbol.research_status.in_(PRIVATE_RESEARCH_STATUSES),
        TickerAnalytics.market == market,
    ]
    cap_condition = _cap_filter(cap_tier)
    if cap_condition is not None:
        base_conditions.append(cap_condition)
    item_conditions = list(base_conditions)
    if new_only:
        item_conditions.append(is_new)

    source = (
        latest.join(Symbol, and_(Symbol.market == market, Symbol.code == latest.c.code))
        .join(
            TickerAnalytics,
            and_(
                TickerAnalytics.market == market,
                TickerAnalytics.code == latest.c.code,
            ),
        )
        .outerjoin(ResearchConditionSubscription, subscription_join)
    )
    observed_count, new_count = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(is_new),
            )
            .select_from(source)
            .where(*base_conditions)
        )
    ).one()
    average_daily_value_mn = case(
        (
            TickerAnalytics.avg_volume_20.isnot(None),
            TickerAnalytics.avg_volume_20 * TickerAnalytics.last_close / 1_000_000.0,
        ),
        else_=None,
    )
    rows = (
        await session.execute(
            select(
                latest.c.code,
                Symbol.name_en,
                Symbol.sector,
                TickerAnalytics.cap_tier,
                latest.c.observed_on,
                TickerAnalytics.as_of_date,
                latest.c.reference_close,
                TickerAnalytics.last_close,
                average_daily_value_mn.label("average_daily_value_mn"),
                latest.c.evidence_mode,
                is_new.label("is_new"),
                func.coalesce(ResearchConditionSubscription.enabled, False).label("subscribed"),
                latest.c.checks,
            )
            .select_from(source)
            .where(*item_conditions)
            .order_by(
                desc(is_new),
                latest.c.observed_on.desc(),
                average_daily_value_mn.desc().nullslast(),
                latest.c.code,
            )
            .limit(limit)
        )
    ).all()
    items = [
        ResearchConditionScanItemOut(
            ticker=code,
            company=company,
            sector=sector,
            cap_tier=cap_tier_value or "unclassified",
            observed_on=observed_on,
            latest_session_date=as_of_date,
            reference_close=reference_close,
            latest_close=last_close,
            close_return_since_observation_pct=round(
                (last_close / reference_close - 1.0) * 100.0, 4
            ),
            average_daily_value_mn=(
                round(average_daily_value, 4) if average_daily_value is not None else None
            ),
            evidence_mode=evidence_mode,
            is_new=bool(new),
            subscribed=bool(subscribed),
            checks=[DossierConditionCheckOut.model_validate(check) for check in checks or []],
        )
        for (
            code,
            company,
            sector,
            cap_tier_value,
            observed_on,
            as_of_date,
            reference_close,
            last_close,
            average_daily_value,
            evidence_mode,
            new,
            subscribed,
            checks,
        ) in rows
    ]

    calibration_rows = list(
        await session.scalars(
            select(ResearchConditionCalibration)
            .where(
                ResearchConditionCalibration.market == market,
                ResearchConditionCalibration.condition_key == condition_key,
                ResearchConditionCalibration.condition_version == definition.version,
                ResearchConditionCalibration.methodology_version == METHODOLOGY_VERSION,
            )
            .order_by(
                ResearchConditionCalibration.evidence_mode,
                ResearchConditionCalibration.horizon_sessions,
            )
        )
    )
    calibrations = [
        ResearchConditionCalibrationOut(
            condition_key=row.condition_key,
            condition_version=row.condition_version,
            evidence_mode=row.evidence_mode,
            horizon_sessions=row.horizon_sessions,
            as_of_date=row.as_of_date,
            history_start_date=row.history_start_date,
            observations=row.observations,
            matured=row.matured,
            pending=row.pending,
            median_return_pct=row.median_return_pct,
            positive_rate_pct=row.positive_rate_pct,
            median_excess_return_pct=row.median_excess_return_pct,
            benchmark_observations=row.benchmark_observations,
            average_max_favorable_pct=row.average_max_favorable_pct,
            average_max_adverse_pct=row.average_max_adverse_pct,
            universe_size=row.universe_size,
            point_in_time_complete=row.point_in_time_complete,
            warning_text=row.warning_text,
        )
        for row in calibration_rows
    ]
    warnings = [
        "Observed means every registered completed-session check is present; it is not a trade "
        "signal, probability estimate, or order.",
    ]
    if any(row.evidence_mode == "reconstructed" for row in calibration_rows):
        warnings.append(
            "Reconstructed outcomes use the current active universe and overlap episodes; use "
            "them for diagnostics, never as forward strategy performance."
        )
    if not any(row.evidence_mode == "forward" and row.matured > 0 for row in calibration_rows):
        warnings.append("The forward sample has not matured enough for an empirical conclusion.")
    return ResearchConditionScanOut(
        tenant_id=tenant_id,
        market=market,
        workspace_id=workspace_id,
        generated_at=dt.datetime.now(dt.UTC),
        latest_session_date=latest_session_date,
        methodology_version=METHODOLOGY_VERSION,
        definition=definition,
        observed_count=int(observed_count or 0),
        new_count=int(new_count or 0),
        returned_count=len(items),
        items=items,
        calibrations=calibrations,
        warnings=warnings,
    )


async def set_condition_subscription(
    session: AsyncSession,
    *,
    tenant_id: str,
    market: str,
    user_id: int,
    code: str,
    condition_key: str,
    enabled: bool,
) -> ResearchConditionSubscriptionOut:
    definition = _definition(condition_key)
    normalized_code = code.strip().upper()
    exists = await session.scalar(
        select(Symbol.code).where(
            Symbol.market == market,
            Symbol.code == normalized_code,
            Symbol.is_active.is_(True),
            Symbol.research_status.in_(PRIVATE_RESEARCH_STATUSES),
        )
    )
    if exists is None:
        raise ValueError("Security is not available in this research tenant")
    row = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "market": market,
        "code": normalized_code,
        "condition_key": condition_key,
        "condition_version": definition.version,
        "methodology_version": METHODOLOGY_VERSION,
        "enabled": enabled,
        "updated_at": dt.datetime.now(dt.UTC),
    }
    stmt = pg_insert(ResearchConditionSubscription).values(row)
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[
                "tenant_id",
                "user_id",
                "market",
                "code",
                "condition_key",
                "condition_version",
                "methodology_version",
            ],
            set_={"enabled": stmt.excluded.enabled, "updated_at": stmt.excluded.updated_at},
        )
    )
    subscription = await session.scalar(
        select(ResearchConditionSubscription).where(
            ResearchConditionSubscription.tenant_id == tenant_id,
            ResearchConditionSubscription.user_id == user_id,
            ResearchConditionSubscription.market == market,
            ResearchConditionSubscription.code == normalized_code,
            ResearchConditionSubscription.condition_key == condition_key,
            ResearchConditionSubscription.condition_version == definition.version,
            ResearchConditionSubscription.methodology_version == METHODOLOGY_VERSION,
        )
    )
    if subscription is None:  # pragma: no cover - database contract violation
        raise RuntimeError("Condition subscription upsert did not return a row")
    return ResearchConditionSubscriptionOut(
        tenant_id=subscription.tenant_id,
        market=subscription.market,
        ticker=subscription.code,
        condition_key=subscription.condition_key,
        condition_version=subscription.condition_version,
        methodology_version=subscription.methodology_version,
        enabled=subscription.enabled,
        last_alerted_on=subscription.last_alerted_on,
    )
