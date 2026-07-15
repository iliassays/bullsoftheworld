"""SEO renderer for /size/{tier} landing pages — DB-gated: DB_TESTS=1 uv run pytest -k seo_size

Sitemap URLs must render real, indexable HTML for crawlers (the CloudFront bot-router sends bots
to /seo/<path>). An unknown tier — or a tier that doesn't exist for the market, like mega on
DSE — must be a noindex 404, never an empty page that looks indexable.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres")
@pytest.mark.asyncio
async def test_size_browse_renders_indexable_list_and_rejects_foreign_tiers() -> None:
    from sqlalchemy import delete, func, select

    from api.seo.render import render_path
    from bulls.core.db import dispose_engine, get_sessionmaker
    from bulls.core.models import Symbol, TickerAnalytics

    await dispose_engine()
    sm = get_sessionmaker()
    code = "T" + uuid.uuid4().hex[:8].upper()
    try:
        async with sm() as session:
            session.add(
                Symbol(
                    market="DSE",
                    code=code,
                    name_en=f"{code} Ltd",
                    name_bn="টেস্ট কোম্পানি",
                    sector="Bank",
                    is_active=True,
                    is_hidden=False,
                    data_status="ready",
                )
            )
            # as_of_date matches the existing freshest date so screens never see a fake max.
            existing_max = await session.scalar(
                select(func.max(TickerAnalytics.as_of_date)).where(TickerAnalytics.market == "DSE")
            )
            session.add(
                TickerAnalytics(
                    market="DSE",
                    code=code,
                    as_of_date=existing_max or dt.date(2026, 7, 1),
                    last_close=100.0,
                    market_cap_mn=15_000.0,
                    cap_tier="large",
                )
            )
            await session.commit()

            html, status = await render_path(session, "DSE", "en/size/large")
            assert status == 200
            assert "noindex" not in html
            assert f"{code} Ltd" in html
            assert "Large cap stocks" in html
            assert "not a recommendation" in html
            assert '<link rel="canonical" href="https://bullsofdhaka.com/en/size/large">' in html

            bn_html, bn_status = await render_path(session, "DSE", "bn/size/large")
            assert bn_status == 200 and "লার্জ ক্যাপ" in bn_html

            # mega is a US-only tier; on DSE it must be a noindex 404.
            mega_html, mega_status = await render_path(session, "DSE", "en/size/mega")
            assert mega_status == 404 and "noindex" in mega_html

            junk_html, junk_status = await render_path(session, "DSE", "en/size/huge")
            assert junk_status == 404 and "noindex" in junk_html
    finally:
        async with sm() as session:
            await session.execute(
                delete(TickerAnalytics).where(
                    TickerAnalytics.market == "DSE", TickerAnalytics.code == code
                )
            )
            await session.execute(delete(Symbol).where(Symbol.market == "DSE", Symbol.code == code))
            await session.commit()
