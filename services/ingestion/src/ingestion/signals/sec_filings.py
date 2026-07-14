"""Material EDGAR filing events for the U.S. official-filings and earnings desks."""

from __future__ import annotations

from bulls.core.models import SecFiling

BEAT = "filings"
EARNINGS_BEAT = "earnings"
RECENT_DAYS = 3
MAX_NOTES_PER_RUN = 20

_EARNINGS_CATEGORIES = frozenset({"earnings", "quarterly_report", "annual_report"})
_MATERIAL_CATEGORIES = frozenset(
    {
        "acquisition",
        "leadership",
        "beneficial_ownership",
        "registration",
        "current_report",
    }
)


def beat_for(filing: SecFiling) -> str | None:
    if filing.category in _EARNINGS_CATEGORIES:
        return EARNINGS_BEAT
    if filing.category in _MATERIAL_CATEGORIES:
        return BEAT
    return None


def render(filing: SecFiling) -> str:
    label = filing.category.replace("_", " ")
    description = (filing.description or "").strip()
    detail = f" - {description}" if description else ""
    report = f", reporting period {filing.report_date}" if filing.report_date else ""
    return (
        f"{filing.code}: new SEC {filing.form} ({label}) filed {filing.filing_date}{report}{detail}. "
        "This is an official filing event, not an interpretation of whether the contents are good "
        "or bad. Read the cited filing before acting. Descriptive, not advice."
    )
