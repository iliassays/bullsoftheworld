"""Public, tenant-scoped acquisition and activation endpoints."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select

from api.analytics_identity import anonymous_session_hash
from api.deps import CurrentLocale, CurrentTenant, DbSession, OptionalUser
from api.ratelimit import client_ip, throttle
from bulls.core.models import BetaFeedback, InstitutionalLead, ProductEvent

router = APIRouter(tags=["growth"])

EventName = Literal[
    "page_view",
    "add_watchlist",
    "remove_watchlist",
    "open_alert",
    "view_ideas",
    "open_idea",
    "create_price_alert",
    "remove_price_alert",
    "ask_stock_research",
    "select_search_result",
    "open_home_alert",
    "open_home_research",
    "click_launch_signup",
    "click_launch_ideas",
    "sign_up_completed",
    "login_completed",
    "onboarding_started",
    "onboarding_step_completed",
    "watchlist_activated",
    "onboarding_skipped",
    "view_institutions",
    "submit_institutional_lead",
    "institutional_lead_submitted",
    "view_trust",
]

_PROPERTY_KEYS = {
    "activation_target",
    "activation_version",
    "alert_kind",
    "board_key",
    "campaign",
    "destination",
    "direction",
    "evaluation",
    "market",
    "medium",
    "query_length",
    "question_kind",
    "result_rank",
    "source",
    "stock_code",
    "step",
    "strategy_pack",
    "surface",
    "watch_count",
}


class ProductEventIn(BaseModel):
    name: EventName
    analytics_consent: Literal[True]
    session_id: str | None = Field(default=None, max_length=64)
    path: str | None = Field(default=None, max_length=512)
    properties: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("properties")
    @classmethod
    def bounded_properties(cls, value):
        clean = {}
        for key, item in value.items():
            if key not in _PROPERTY_KEYS or len(clean) >= 12:
                continue
            clean[key] = item[:128] if isinstance(item, str) else item
        return clean


@router.post("/product-events", status_code=status.HTTP_202_ACCEPTED)
async def record_product_event(
    body: ProductEventIn,
    request: Request,
    tenant: CurrentTenant,
    locale: CurrentLocale,
    session: DbSession,
    viewer: OptionalUser,
) -> dict[str, str]:
    await throttle(f"product-event:{tenant.name}:{client_ip(request)}", limit=600, window_s=3600)
    session.add(
        ProductEvent(
            tenant_id=tenant.name,
            market=tenant.market,
            name=body.name,
            user_id=viewer.id if viewer else None,
            session_hash=anonymous_session_hash(tenant.name, body.session_id),
            locale=locale,
            path=body.path,
            properties=body.properties,
        )
    )
    return {"status": "accepted"}


class InstitutionalLeadIn(BaseModel):
    organization: str = Field(min_length=2, max_length=160)
    contact_name: str = Field(min_length=2, max_length=120)
    work_email: str = Field(
        min_length=5,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    role: str = Field(min_length=2, max_length=80)
    use_case: str = Field(min_length=20, max_length=1200)
    source: str = Field(default="institutional_page", max_length=64, pattern=r"^[a-z0-9_-]+$")
    consent: Literal[True]
    website: str = Field(default="", max_length=200)  # honeypot; people never see this field

    @field_validator("organization", "contact_name", "role", "use_case")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return " ".join(value.split())


@router.post("/institutional-leads", status_code=status.HTTP_202_ACCEPTED)
async def create_institutional_lead(
    body: InstitutionalLeadIn,
    request: Request,
    tenant: CurrentTenant,
    session: DbSession,
) -> dict[str, str]:
    await throttle(f"institutional-lead:{tenant.name}:{client_ip(request)}", limit=5, window_s=3600)
    if body.website:
        return {"status": "accepted"}

    email = body.work_email.strip().lower()
    duplicate = await session.scalar(
        select(InstitutionalLead.id).where(
            InstitutionalLead.tenant_id == tenant.name,
            InstitutionalLead.work_email == email,
            InstitutionalLead.created_at >= dt.datetime.now(dt.UTC) - dt.timedelta(days=1),
        )
    )
    if duplicate is None:
        now = dt.datetime.now(dt.UTC)
        session.add(
            InstitutionalLead(
                tenant_id=tenant.name,
                market=tenant.market,
                organization=body.organization,
                contact_name=body.contact_name,
                work_email=email,
                role=body.role,
                use_case=body.use_case,
                source=body.source,
                consented_at=now,
            )
        )
    return {"status": "accepted"}


FeedbackKind = Literal["useful", "unclear", "incorrect", "missing", "other"]


class BetaFeedbackIn(BaseModel):
    kind: FeedbackKind
    message: str = Field(default="", max_length=1200)
    path: str = Field(min_length=1, max_length=512)
    symbol_code: str | None = Field(
        default=None,
        max_length=32,
        pattern=r"^[A-Z0-9.\-]{1,32}$",
    )
    contact_consent: bool = False
    website: str = Field(default="", max_length=200)

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("path")
    @classmethod
    def relative_path_only(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("path must be a same-site absolute path")
        return value

    @field_validator("symbol_code", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        return value.strip().upper() if isinstance(value, str) and value.strip() else None

    @model_validator(mode="after")
    def require_actionable_detail(self):
        if self.kind != "useful" and len(self.message) < 10:
            raise ValueError("please add at least 10 characters of detail")
        return self


@router.post("/beta-feedback", status_code=status.HTTP_202_ACCEPTED)
async def create_beta_feedback(
    body: BetaFeedbackIn,
    request: Request,
    tenant: CurrentTenant,
    locale: CurrentLocale,
    session: DbSession,
    viewer: OptionalUser,
) -> dict[str, str]:
    if not tenant.research_beta:
        raise HTTPException(status_code=404, detail="Beta feedback is unavailable")
    await throttle(f"beta-feedback:{tenant.name}:{client_ip(request)}", limit=20, window_s=3600)
    if body.website:
        return {"status": "accepted"}

    can_contact = body.contact_consent and viewer is not None
    session.add(
        BetaFeedback(
            tenant_id=tenant.name,
            market=tenant.market,
            locale=locale,
            kind=body.kind,
            message=body.message,
            path=body.path,
            symbol_code=body.symbol_code,
            user_id=viewer.id if can_contact else None,
            contact_consent=can_contact,
        )
    )
    return {"status": "accepted"}
