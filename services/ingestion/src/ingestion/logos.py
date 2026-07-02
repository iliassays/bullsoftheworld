"""Onboard company logos. DSE hosts none, so we hop to each company's own website (from the DSE
"Web Address" field) and cache its best icon (apple-touch-icon > declared icon > og:image > favicon).

Bytes are stored in `company_logos` and served by the API; a missing/failed row falls back to a
monogram in the UI. `status` + `checked_at` let a re-run skip names looked at recently instead of
re-hitting dead sites. We only ever GET, and keep a row only when the response is a real image within
a size cap — never anything executable.

    uv run python -m ingestion.logos backfill   # fetch for every symbol
    uv run python -m ingestion.logos daily        # only symbols not checked within RECHECK_DAYS
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re
import sys
from urllib.parse import urljoin, urlparse

import httpx
from selectolax.parser import HTMLParser
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.db import get_sessionmaker
from bulls.core.models import CompanyLogo, Symbol
from bulls.market_data import get_provider

MARKET = "DSE"
RECHECK_DAYS = 30  # in daily mode, skip names already checked this recently
_CONCURRENCY = 8  # be polite to DSE + company sites
_MIN_BYTES = 100
_MAX_BYTES = 1_000_000
# Full browser-ish headers — a bare UA gets 403'd by some company sites.
_HDRS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
# DSE sometimes lists a dead/stale Web Address (e.g. RUPALIBANK -> the defunct .org). Override with
# the real domain here; the fetcher + favicon fallback use this instead of the DSE value.
_OVERRIDES: dict[str, str] = {
    "RUPALIBANK": "https://rupalibank.com.bd",
}


def _favicon_service(domain: str) -> str:
    """A favicon service that already has icons cached for sites that block or time out on us. It
    returns 404 for domains it doesn't know, which we skip (so we never store its default globe)."""
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"


def pick_icons(html: str, base: str) -> list[str]:
    """Ordered best-guess icon URLs for a homepage: apple-touch-icon (largest) > declared icon
    (largest) > og:image > /favicon.ico. Absolute-resolved, de-duplicated."""
    tree = HTMLParser(html)
    cands: list[tuple[int, int, str]] = []
    for ln in tree.css("link"):
        rel = (ln.attributes.get("rel") or "").lower()
        href = ln.attributes.get("href")
        if not href:
            continue
        sizes = ln.attributes.get("sizes") or ""
        px = max([int(x) for x in re.findall(r"(\d+)x\d+", sizes)] or [0])
        if "apple-touch-icon" in rel:
            cands.append((3, px or 180, urljoin(base, href)))
        elif "icon" in rel:
            cands.append((2, px, urljoin(base, href)))
    for mt in tree.css("meta"):
        if (mt.attributes.get("property") or "") == "og:image" and mt.attributes.get("content"):
            cands.append((1, 0, urljoin(base, mt.attributes["content"])))
    cands.sort(key=lambda c: (c[0], c[1]), reverse=True)
    ordered = [c[2] for c in cands]
    ordered.append(urljoin(base, "/favicon.ico"))
    seen: set[str] = set()
    return [u for u in ordered if not (u in seen or seen.add(u))]


async def _download_image(client: httpx.AsyncClient, url: str) -> dict | None:
    """GET `url`; return an image row fragment if it's a real image within the size cap, else None."""
    try:
        r = await client.get(url, headers=_HDRS)
    except Exception:
        return None
    ct = r.headers.get("content-type", "").split(";")[0].strip().lower()
    if r.status_code == 200 and ct.startswith("image/") and _MIN_BYTES < len(r.content) <= _MAX_BYTES:
        return {"image": r.content, "content_type": ct, "source_url": str(r.url), "status": "ok"}
    return None


async def _fetch_one(client: httpx.AsyncClient, provider, code: str) -> dict:
    """Resolve one company's logo → an upsert row dict (image + status).

    Order: the company site's own declared icons, then a favicon service (which has icons cached for
    sites that block or time out on us). An override domain wins over the DSE-listed one.
    """
    row: dict = {"market": MARKET, "code": code, "image": None, "content_type": None, "source_url": None}
    site = _OVERRIDES.get(code)
    if not site:
        try:
            site = await provider.get_company_website(code)
        except Exception:
            site = None
    if not site:
        row["status"] = "no_site"
        return row
    if not site.startswith(("http://", "https://")):
        site = "http://" + site

    # 1. The company site's own icons (best quality when reachable).
    home_ok = False
    try:
        home = await client.get(site, headers=_HDRS)
        home.raise_for_status()
        home_ok = True
    except Exception:
        home = None
    if home is not None:
        for icon in pick_icons(home.text, str(home.url))[:4]:
            got = await _download_image(client, icon)
            if got:
                row.update(got)
                return row

    # 2. Favicon service fallback — works even when the site itself blocks/times out on us.
    domain = urlparse(site).netloc
    if domain:
        got = await _download_image(client, _favicon_service(domain))
        if got:
            row.update(got)
            return row

    row["status"] = "no_icon" if home_ok else "error"
    return row


async def collect(*, recheck_days: int) -> dict[str, int]:
    provider = get_provider(MARKET)
    sm = get_sessionmaker()
    async with sm() as session:
        codes = list(await session.scalars(select(Symbol.code).where(Symbol.market == MARKET)))
        cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=recheck_days)
        # Only skip names we already have a logo for — so re-runs keep retrying the failures.
        recent = set(
            await session.scalars(
                select(CompanyLogo.code).where(
                    CompanyLogo.market == MARKET,
                    CompanyLogo.status == "ok",
                    CompanyLogo.checked_at >= cutoff,
                )
            )
        )
    todo = [c for c in codes if c not in recent]
    stats = {"total": len(codes), "checked": 0, "ok": 0, "no_site": 0, "no_icon": 0, "error": 0}
    sem = asyncio.Semaphore(_CONCURRENCY)

    async with httpx.AsyncClient(timeout=15, follow_redirects=True, verify=False) as client:

        async def worker(code: str) -> dict:
            async with sem:
                return await _fetch_one(client, provider, code)

        # Process (and commit) in batches so a long run persists progress incrementally.
        for i in range(0, len(todo), 50):
            rows = await asyncio.gather(*(worker(c) for c in todo[i : i + 50]))
            now = dt.datetime.now(dt.UTC)
            async with sm() as session:
                for row in rows:
                    stats["checked"] += 1
                    stats[row["status"]] = stats.get(row["status"], 0) + 1
                    await session.execute(
                        pg_insert(CompanyLogo)
                        .values(**row, checked_at=now)
                        .on_conflict_do_update(
                            index_elements=["market", "code"],
                            set_={
                                "image": row["image"],
                                "content_type": row["content_type"],
                                "source_url": row["source_url"],
                                "status": row["status"],
                                "checked_at": now,
                            },
                        )
                    )
                await session.commit()
            print(
                f"[logos] {stats['checked']}/{len(todo)} · ok={stats['ok']} "
                f"no_site={stats['no_site']} no_icon={stats['no_icon']} err={stats['error']}",
                flush=True,
            )
    return stats


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    recheck = 0 if mode == "backfill" else RECHECK_DAYS
    print(f"[logos] {mode}: fetching company logos (recheck_days={recheck})")
    stats = asyncio.run(collect(recheck_days=recheck))
    print(f"[logos] done: {stats}")


if __name__ == "__main__":
    main()
