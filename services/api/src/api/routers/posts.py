"""Posts + cashtags (build step 3). Stub router showing the shape."""

from __future__ import annotations

import re

from fastapi import APIRouter

from api.deps import CurrentTenant

router = APIRouter(prefix="/posts", tags=["posts"])

# Cashtag = $ followed by 2-16 uppercase alphanumerics (validated against symbols at write time).
CASHTAG_RE = re.compile(r"\$([A-Z0-9]{2,16})")


def parse_cashtags(body: str) -> list[str]:
    return list(dict.fromkeys(CASHTAG_RE.findall(body)))


@router.get("")
async def list_posts(tenant: CurrentTenant) -> dict:
    # step 3: query feed for tenant.name, newest first, paginated
    return {"tenant": tenant.name, "posts": []}
