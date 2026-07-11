"""SEO routes: server-rendered HTML for bots/social scrapers.

CloudFront rewrites a crawler request for `/<path>` to `/seo/<path>` and forwards it here (humans
keep getting the SPA from S3). robots.txt + sitemap.xml are served as static files from S3 (the
sitemap is generated at deploy from this same data), so they aren't handled here.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from api.deps import CurrentTenant, DbSession
from api.seo.render import render_path

router = APIRouter(tags=["seo"])


@router.get("/seo/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
async def seo_render(full_path: str, tenant: CurrentTenant, session: DbSession) -> HTMLResponse:
    domain = next(
        (d for d in tenant.domains if "." in d and not d.endswith(".localhost")),
        "bullsofdhaka.com",
    )
    html, status = await render_path(
        session,
        tenant.market,
        full_path,
        site=f"https://{domain}",
        brand=tenant.display_name,
        default_lang=tenant.locale,
        supported_locales=tuple(tenant.supported_locales),
    )
    # Short cache: crawlers can re-fetch; content is EOD/15-min-delayed so it needn't be instant.
    return HTMLResponse(
        content=html,
        status_code=status,
        headers={"Cache-Control": "public, max-age=900"},
    )
