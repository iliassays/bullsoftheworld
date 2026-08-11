from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, select

from api.main import app
from api.routers.growth import BetaFeedbackIn, InstitutionalLeadIn, ProductEventIn
from bulls.core.db import dispose_engine, get_sessionmaker
from bulls.core.models import BetaFeedback, InstitutionalLead, ProductEvent


def test_product_event_properties_are_allowlisted_and_bounded() -> None:
    event = ProductEventIn(
        name="add_watchlist",
        analytics_consent=True,
        session_id="client-1",
        path="/bn/s/GP",
        properties={
            "stock_code": "GP",
            "market": "DSE",
            "question": "free-form research question must not enter first-party analytics",
            "campaign": "x" * 200,
        },
    )

    assert event.properties == {
        "stock_code": "GP",
        "market": "DSE",
        "campaign": "x" * 128,
    }


def test_product_event_rejects_unknown_names() -> None:
    with pytest.raises(ValidationError):
        ProductEventIn(name="arbitrary_event", analytics_consent=True)  # type: ignore[arg-type]


def test_product_event_requires_analytics_consent() -> None:
    with pytest.raises(ValidationError):
        ProductEventIn(name="add_watchlist", analytics_consent=False)


def test_atlas_product_event_is_allowlisted_and_privacy_bounded() -> None:
    event = ProductEventIn(
        name="atlas_workflow_stage_opened",
        analytics_consent=True,
        session_id="atlas-session",
        path="/companies/:ticker",
        properties={
            "atlas_stage": "investigate",
            "atlas_version": "orientation-v1",
            "entry_point": "discover",
            "route_group": "investigate",
            "result_count": 12,
            "ticker": "NXTC",
            "research_question": "free-form text must never be retained",
        },
    )

    assert event.properties == {
        "atlas_stage": "investigate",
        "atlas_version": "orientation-v1",
        "entry_point": "discover",
        "route_group": "investigate",
        "result_count": 12,
    }


def test_institutional_lead_requires_explicit_consent_and_valid_email() -> None:
    valid = {
        "organization": "Example Securities",
        "contact_name": "Research Lead",
        "work_email": "lead@example.com",
        "role": "Head of Research",
        "use_case": "We want disclosure monitoring for our research and client service teams.",
        "consent": True,
    }
    assert InstitutionalLeadIn(**valid).organization == "Example Securities"

    with pytest.raises(ValidationError):
        InstitutionalLeadIn(**{**valid, "consent": False})
    with pytest.raises(ValidationError):
        InstitutionalLeadIn(**{**valid, "work_email": "not-an-email"})


def test_beta_feedback_normalizes_and_requires_actionable_detail() -> None:
    feedback = BetaFeedbackIn(
        kind="incorrect",
        message="  The latest price is   stale. ",
        path="/bn/s/GP",
        symbol_code="gp",
    )
    assert feedback.message == "The latest price is stale."
    assert feedback.symbol_code == "GP"

    with pytest.raises(ValidationError):
        BetaFeedbackIn(kind="incorrect", message="wrong", path="/bn/s/GP")
    with pytest.raises(ValidationError):
        BetaFeedbackIn(kind="useful", path="https://example.com/bn/s/GP")


def test_beta_feedback_useful_vote_can_be_message_free() -> None:
    feedback = BetaFeedbackIn(kind="useful", path="/en/markets")
    assert feedback.message == ""


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres + Redis")
def test_growth_events_and_institutional_leads_persist() -> None:
    marker = uuid.uuid4().hex
    email = f"growth-{marker}@example.com"
    with TestClient(app) as client:
        event = client.post(
            "/product-events",
            json={
                "name": "click_launch_signup",
                "analytics_consent": True,
                "session_id": marker,
                "path": "/bn",
                "properties": {"source": "test", "campaign": marker},
            },
        )
        assert event.status_code == 202, event.text
        lead = client.post(
            "/institutional-leads",
            json={
                "organization": "Test Securities",
                "contact_name": "Test Research Lead",
                "work_email": email,
                "role": "Head of Research",
                "use_case": "We need a test workflow for source-linked disclosure monitoring.",
                "source": "institutional_page",
                "consent": True,
                "website": "",
            },
        )
        assert lead.status_code == 202, lead.text
        disabled_feedback = client.post(
            "/beta-feedback",
            json={
                "kind": "missing",
                "message": f"Missing dividend context {marker}",
                "path": "/bn/s/GP",
                "symbol_code": "gp",
                "contact_consent": True,
                "website": "",
            },
        )
        assert disabled_feedback.status_code == 404, disabled_feedback.text
        feedback = client.post(
            "/beta-feedback",
            headers={"X-Tenant-Host": "bullsofwallst.com", "X-Locale": "en"},
            json={
                "kind": "missing",
                "message": f"Missing filing context {marker}",
                "path": "/en/s/AAPL",
                "symbol_code": "aapl",
                "contact_consent": True,
                "website": "",
            },
        )
        assert feedback.status_code == 202, feedback.text

    async def verify_and_clean() -> None:
        await dispose_engine()
        async with get_sessionmaker()() as session:
            saved_event = await session.scalar(
                select(ProductEvent).where(
                    ProductEvent.properties["campaign"].as_string() == marker
                )
            )
            saved_lead = await session.scalar(
                select(InstitutionalLead).where(InstitutionalLead.work_email == email)
            )
            saved_feedback = await session.scalar(
                select(BetaFeedback).where(BetaFeedback.message.contains(marker))
            )
            assert saved_event is not None and saved_event.tenant_id == "bullsofdhaka"
            assert saved_event.session_hash is not None and marker not in saved_event.session_hash
            assert saved_lead is not None and saved_lead.status == "new"
            assert saved_feedback is not None
            assert saved_feedback.tenant_id == "bullsofwallst"
            assert saved_feedback.locale == "en"
            assert saved_feedback.symbol_code == "AAPL"
            assert saved_feedback.user_id is None
            assert saved_feedback.contact_consent is False
            await session.execute(
                delete(ProductEvent).where(
                    ProductEvent.properties["campaign"].as_string() == marker
                )
            )
            await session.execute(
                delete(InstitutionalLead).where(InstitutionalLead.work_email == email)
            )
            await session.execute(delete(BetaFeedback).where(BetaFeedback.message.contains(marker)))
            await session.commit()
        await dispose_engine()

    asyncio.run(verify_and_clean())
