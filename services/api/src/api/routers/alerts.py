"""Alerts inbox + user-set price alerts.

The inbox is written at event time by ingestion (fan-out per watcher/holder), so every read here
is a plain indexed scan — the 60s bell poll costs one COUNT on (user_id, read_at).
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from api.deps import CurrentLocale, CurrentTenant, CurrentUser, DbSession, enforce_market_feature
from bulls.core.models import AlertEvent, PriceAlert, Symbol

router = APIRouter(prefix="/alerts", tags=["alerts"])

MAX_PRICE_ALERTS_PER_USER = 30


class AlertOut(BaseModel):
    id: int
    kind: str
    code: str | None
    title: str
    body: str | None
    created_at: dt.datetime
    read: bool


class PriceAlertIn(BaseModel):
    code: str
    level: float = Field(gt=0)
    direction: str = Field(pattern="^(above|below)$")


class PriceAlertOut(BaseModel):
    id: int
    code: str
    level: float
    direction: str
    triggered_at: dt.datetime | None


def _pick(i18n: dict | None, locale: str) -> str | None:
    if not i18n:
        return None
    return i18n.get(locale) or i18n.get("en") or next(iter(i18n.values()), None)


@router.get("")
async def list_alerts(
    user: CurrentUser,
    tenant: CurrentTenant,
    session: DbSession,
    locale: CurrentLocale,
    limit: int = Query(30, le=100),
    offset: int = Query(0, ge=0),
) -> list[AlertOut]:
    rows = (
        await session.scalars(
            select(AlertEvent)
            .where(
                AlertEvent.tenant_id == tenant.name,
                AlertEvent.user_id == user.id,
                AlertEvent.market == tenant.market,
            )
            .order_by(AlertEvent.created_at.desc(), AlertEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [
        AlertOut(
            id=a.id,
            kind=a.kind,
            code=a.code,
            title=_pick(a.title_i18n, locale) or "",
            body=_pick(a.body_i18n, locale),
            created_at=a.created_at,
            read=a.read_at is not None,
        )
        for a in rows
    ]


@router.get("/unread-count")
async def unread_count(
    user: CurrentUser, tenant: CurrentTenant, session: DbSession
) -> dict[str, int]:
    n = await session.scalar(
        select(func.count())
        .select_from(AlertEvent)
        .where(
            AlertEvent.user_id == user.id,
            AlertEvent.tenant_id == tenant.name,
            AlertEvent.market == tenant.market,
            AlertEvent.read_at.is_(None),
        )
    )
    return {"unread": int(n or 0)}


@router.post("/mark-read")
async def mark_read(user: CurrentUser, tenant: CurrentTenant, session: DbSession) -> dict[str, str]:
    await session.execute(
        update(AlertEvent)
        .where(
            AlertEvent.user_id == user.id,
            AlertEvent.tenant_id == tenant.name,
            AlertEvent.market == tenant.market,
            AlertEvent.read_at.is_(None),
        )
        .values(read_at=func.now())
    )
    return {"status": "ok"}


@router.get("/price")
async def list_price_alerts(
    user: CurrentUser,
    tenant: CurrentTenant,
    session: DbSession,
    code: str | None = Query(None),
) -> list[PriceAlertOut]:
    enforce_market_feature(tenant, "price_alerts")
    stmt = select(PriceAlert).where(
        PriceAlert.tenant_id == tenant.name,
        PriceAlert.user_id == user.id,
        PriceAlert.market == tenant.market,
    )
    if code:
        stmt = stmt.where(PriceAlert.code == code.upper())
    rows = (await session.scalars(stmt.order_by(PriceAlert.created_at.desc()))).all()
    return [
        PriceAlertOut(
            id=a.id, code=a.code, level=a.level, direction=a.direction, triggered_at=a.triggered_at
        )
        for a in rows
    ]


@router.post("/price", status_code=201)
async def create_price_alert(
    body: PriceAlertIn, user: CurrentUser, tenant: CurrentTenant, session: DbSession
) -> PriceAlertOut:
    enforce_market_feature(tenant, "price_alerts")
    code = body.code.upper()
    symbol = await session.get(Symbol, (tenant.market, code))
    if symbol is None or not symbol.is_public_research:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")
    active = await session.scalar(
        select(func.count())
        .select_from(PriceAlert)
        .where(
            PriceAlert.tenant_id == tenant.name,
            PriceAlert.user_id == user.id,
            PriceAlert.market == tenant.market,
            PriceAlert.triggered_at.is_(None),
        )
    )
    if int(active or 0) >= MAX_PRICE_ALERTS_PER_USER:
        raise HTTPException(status_code=429, detail="Too many active price alerts")
    alert = PriceAlert(
        tenant_id=tenant.name,
        user_id=user.id,
        market=tenant.market,
        code=code,
        level=body.level,
        direction=body.direction,
    )
    session.add(alert)
    await session.flush()
    return PriceAlertOut(
        id=alert.id,
        code=alert.code,
        level=alert.level,
        direction=alert.direction,
        triggered_at=None,
    )


@router.delete("/price/{alert_id}", status_code=204)
async def delete_price_alert(
    alert_id: int, user: CurrentUser, tenant: CurrentTenant, session: DbSession
) -> None:
    enforce_market_feature(tenant, "price_alerts")
    alert = await session.get(PriceAlert, alert_id)
    if (
        alert is not None
        and alert.user_id == user.id
        and alert.tenant_id == tenant.name
        and alert.market == tenant.market
    ):
        await session.delete(alert)
