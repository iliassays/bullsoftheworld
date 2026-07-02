"""Company logos, fetched at onboarding from each company's own website.

The DSE portal has no logos, but its company page lists a "Web Address"; we hop there, pull the
site's best icon (apple-touch-icon / declared icon / favicon), and cache the bytes here. `status`
records the outcome (ok / no_site / no_icon / error) with `checked_at` so a re-run can skip names we
looked at recently instead of hammering dead sites. Absent/failed rows fall back to a monogram in UI.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bulls.core.db import Base


class CompanyLogo(Base):
    __tablename__ = "company_logos"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    image: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok | no_site | no_icon | error
    checked_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
