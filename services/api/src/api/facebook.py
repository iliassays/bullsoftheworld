"""Facebook Page posting via the Graph API.

Posts to the Bulls of Dhaka page using a permanent Page access token (FB_PAGE_TOKEN / FB_PAGE_ID).
Two post types: a text/link post (/feed) and a photo post with caption (/photos). All content is
descriptive, never financial advice — same line as the portal.
"""

from __future__ import annotations

import logging

import httpx

from bulls.core.config import get_settings

log = logging.getLogger(__name__)


class FacebookError(RuntimeError):
    pass


def _base() -> tuple[str, str, str]:
    s = get_settings()
    if not s.fb_enabled:
        raise FacebookError("Facebook not configured (FB_PAGE_ID / FB_PAGE_TOKEN missing)")
    return f"https://graph.facebook.com/{s.fb_graph_version}", s.fb_page_id, s.fb_page_token


async def page_info() -> dict:
    """Non-publishing check: returns the page name + follower count (verifies the token works)."""
    base, page_id, token = _base()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{base}/{page_id}",
            params={"fields": "name,fan_count,link", "access_token": token},
        )
    if r.status_code >= 300:
        raise FacebookError(f"page_info failed {r.status_code}: {r.text}")
    return r.json()


async def post_text(message: str, link: str | None = None) -> str:
    """Publish a text (optionally with a link) post. Returns the new post id."""
    base, page_id, token = _base()
    data = {"message": message, "access_token": token}
    if link:
        data["link"] = link
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{base}/{page_id}/feed", data=data)
    if r.status_code >= 300:
        raise FacebookError(f"post_text failed {r.status_code}: {r.text}")
    return r.json().get("id", "")


async def post_photo(image_url: str, caption: str = "") -> str:
    """Publish a photo (by public image URL) with a caption. Returns the post/photo id."""
    base, page_id, token = _base()
    data = {"url": image_url, "caption": caption, "access_token": token}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{base}/{page_id}/photos", data=data)
    if r.status_code >= 300:
        raise FacebookError(f"post_photo failed {r.status_code}: {r.text}")
    j = r.json()
    return j.get("post_id") or j.get("id", "")


async def post_photo_bytes(png: bytes, caption: str = "") -> str:
    """Publish a generated image (raw PNG bytes) with a caption. Returns the post/photo id."""
    base, page_id, token = _base()
    files = {"source": ("card.png", png, "image/png")}
    data = {"caption": caption, "access_token": token}
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(f"{base}/{page_id}/photos", data=data, files=files)
    if r.status_code >= 300:
        raise FacebookError(f"post_photo_bytes failed {r.status_code}: {r.text}")
    j = r.json()
    return j.get("post_id") or j.get("id", "")
