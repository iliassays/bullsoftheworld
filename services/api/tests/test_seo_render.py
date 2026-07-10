"""SEO HTML renderer (served to bots/social scrapers) — DB-gated: DB_TESTS=1 uv run pytest -k seo_render

Verifies the crawler HTML carries real per-page title/description/canonical/hreflang/JSON-LD, that
a stock page shows its price WITH the delayed marker (honesty, CLAUDE.md #4), and that unknown /
private paths are noindex.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest


@pytest.mark.asyncio
async def test_us_seo_uses_english_default_and_enabled_research_surfaces() -> None:
    from api.seo.render import render_path

    home, status = await render_path(
        None,
        "US",
        "",
        site="https://bullsofwallst.com",
        brand="Bulls of Wall Street",
    )
    assert status == 200
    assert 'hreflang="x-default" href="https://bullsofwallst.com/en"' in home
    assert '"target": "https://bullsofwallst.com/en/s/{search_term_string}"' in home
    assert "fundamentals" in home
    assert "automated desks" not in home

    markets, markets_status = await render_path(None, "US", "en/markets")
    assert markets_status == 200
    assert "Market screens" in markets


@pytest.mark.skipif(not os.getenv("DB_TESTS"), reason="set DB_TESTS=1 with Postgres")
@pytest.mark.asyncio
async def test_seo_renderer_stock_home_pattern_and_noindex() -> None:
    from api.seo.render import render_path
    from bulls.core.db import dispose_engine, get_sessionmaker
    from bulls.core.models import Symbol
    from bulls.core.models.quote import DailyBar, QuoteSnapshot

    await dispose_engine()
    sm = get_sessionmaker()
    code = "T" + uuid.uuid4().hex[:8].upper()
    us_code = "U" + uuid.uuid4().hex[:8].upper()
    async with sm() as session:
        session.add(
            Symbol(
                market="DSE",
                code=code,
                name_en=f"{code} Ltd",
                name_bn="টেস্ট কোম্পানি",
                sector="Bank",
                category="A",
                is_active=True,
                is_hidden=False,
                data_status="ready",
            )
        )
        session.add(
            QuoteSnapshot(
                market="DSE",
                code=code,
                ltp=123.4,
                change=1.2,
                change_pct=0.98,
                high=124.0,
                low=122.0,
                close=123.4,
                volume=1000,
                trades=10,
                as_of=dt.datetime(2026, 7, 2, 8, 0, tzinfo=dt.UTC),
                is_delayed=True,
            )
        )
        session.add(
            Symbol(
                market="US",
                code=us_code,
                name_en=f"{us_code} Corp",
                sector="Technology",
                is_active=True,
                is_hidden=False,
                data_status="ready",
            )
        )
        session.add(
            DailyBar(
                market="US",
                code=us_code,
                date=dt.date(2026, 7, 2),
                open=100.0,
                high=104.0,
                low=99.0,
                close=102.0,
                adjusted_close=51.0,
                volume=100_000,
                source="test",
            )
        )
        await session.commit()

        # English stock page
        html, status = await render_path(session, "DSE", f"en/s/{code}")
        assert status == 200
        assert f"{code} Ltd" in html and code in html
        assert f'<link rel="canonical" href="https://bullsofdhaka.com/en/s/{code}">' in html
        assert (
            'hreflang="bn"' in html and 'hreflang="en"' in html and 'hreflang="x-default"' in html
        )
        assert "৳123.4" in html
        assert "delayed" in html  # honesty: never a bare price
        assert "application/ld+json" in html
        assert "noindex" not in html  # a real stock page is indexable

        # EOD-only markets expose the adjusted close and never claim intraday/fundamental coverage.
        us_html, us_status = await render_path(
            session,
            "US",
            f"en/s/{us_code}",
            site="https://bullsofwallst.com",
            brand="Bulls of Wall Street",
        )
        assert us_status == 200
        assert "$51.00" in us_html
        assert "Latest EOD close" in us_html
        assert "15-min" not in us_html
        assert "fundamentals" not in us_html

        # Bangla uses the Bangla name
        html_bn, _ = await render_path(session, "DSE", f"bn/s/{code}")
        assert "টেস্ট কোম্পানি" in html_bn

        # Home: Organization + WebSite structured data
        home, _ = await render_path(session, "DSE", "en")
        assert home.count("application/ld+json") == 2 and "SearchAction" in home

        # Pattern detail page
        pat, _ = await render_path(session, "DSE", "en/learn/patterns/double_top")
        assert "Double Top" in pat

        # Unknown ticker → noindex + 404
        nf, nf_status = await render_path(session, "DSE", "en/s/NOPENOTREAL")
        assert nf_status == 404 and "noindex" in nf

        # Private path → valid but noindex
        priv, _ = await render_path(session, "DSE", "en/portfolio")
        assert "noindex" in priv
    async with sm() as session:
        obj = await session.get(Symbol, ("DSE", code))
        if obj:
            await session.delete(obj)
        q = await session.get(QuoteSnapshot, ("DSE", code))
        if q:
            await session.delete(q)
        us_bar = await session.get(DailyBar, ("US", us_code, dt.date(2026, 7, 2)))
        if us_bar:
            await session.delete(us_bar)
        us_symbol = await session.get(Symbol, ("US", us_code))
        if us_symbol:
            await session.delete(us_symbol)
        await session.commit()
