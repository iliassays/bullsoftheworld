"""SQL projection of the shared DSE disclosure-materiality policy."""

from __future__ import annotations

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

from bulls.analytics.disclosure_materiality import (
    ALWAYS_MATERIAL_CATEGORIES,
    STRUCTURED_MATERIAL_KEYS,
)
from bulls.core.models import Announcement


def material_dse_announcement_filter() -> ColumnElement[bool]:
    """Return a SQL predicate equivalent to ``is_material_dse_disclosure``."""

    structured = [
        and_(
            Announcement.category == category,
            Announcement.details.is_not(None),
            or_(*(Announcement.details[key].astext.is_not(None) for key in keys)),
        )
        for category, keys in STRUCTURED_MATERIAL_KEYS.items()
    ]
    return or_(
        Announcement.category.in_(ALWAYS_MATERIAL_CATEGORIES),
        *structured,
    )
