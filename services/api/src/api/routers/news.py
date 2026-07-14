"""A symbol's classified news/announcements for the News tab — descriptive, ranked by recency.

We serve the decoded `details` (EPS now/prior, dividend rate, record date, …) alongside the headline
so the frontend can render a trader-friendly card per locale. Low-importance "other" items (exchange
greetings, awareness notices, admin re-posts) are kept in the DB but hidden from this feed.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from api.deps import CurrentTenant, DbSession, enforce_market_feature
from bulls.core.markets import get_market_profile
from bulls.core.models import Announcement, SecFiling, Symbol

router = APIRouter(tags=["news"])

# Categories surfaced to users — material to a trader. "other" stays in the DB but is hidden here.
_SHOWN_CATEGORIES = (
    "dividend",
    "earnings",
    "board_meeting",
    "rating",
    "halt",
    "corporate_action",
    "insider",
    "psi",
)


class NewsOut(BaseModel):
    published_at: str
    category: str
    strength: int
    headline: str
    details: dict[str, Any] | None = None
    url: str | None = None


_SEC_STRENGTH = {
    "annual_report": 95,
    "quarterly_report": 90,
    "earnings": 90,
    "acquisition": 85,
    "beneficial_ownership": 75,
    "leadership": 70,
    "registration": 70,
    "proxy": 55,
    "current_report": 50,
}


def _sec_headline(row: SecFiling) -> str:
    label = row.category.replace("_", " ").title()
    description = (row.description or "").strip()
    return f"{label}: {description}" if description else f"{label} ({row.form})"


@router.get("/symbols/{code}/news")
async def symbol_news(
    code: str, tenant: CurrentTenant, session: DbSession, limit: int = Query(40, le=100)
) -> list[NewsOut]:
    enforce_market_feature(tenant, "official_disclosures")
    code = code.upper()
    symbol = await session.get(Symbol, (tenant.market, code))
    if symbol is None or not symbol.is_public_research:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")
    if get_market_profile(tenant.market).features.sec_filings:
        filings = await session.scalars(
            select(SecFiling)
            .where(SecFiling.market == tenant.market, SecFiling.code == code)
            .order_by(SecFiling.filing_date.desc(), SecFiling.accepted_at.desc())
            .limit(limit)
        )
        return [
            NewsOut(
                published_at=str(row.filing_date),
                category=row.category,
                strength=_SEC_STRENGTH.get(row.category, 45),
                headline=_sec_headline(row),
                details={
                    "source": "SEC EDGAR",
                    "form": row.form,
                    "report_date": str(row.report_date) if row.report_date else None,
                    "items": row.items,
                    "accession_number": row.accession_number,
                },
                url=row.filing_url,
            )
            for row in filings
        ]
    rows = await session.scalars(
        select(Announcement)
        .where(
            Announcement.market == tenant.market,
            Announcement.code == code,
            Announcement.category.in_(_SHOWN_CATEGORIES),
        )
        .order_by(Announcement.published_at.desc(), Announcement.strength.desc())
        .limit(limit)
    )
    return [
        NewsOut(
            published_at=str(a.published_at),
            category=a.category,
            strength=a.strength,
            headline=a.headline,
            details=a.details,
            url=None,
        )
        for a in rows
    ]
