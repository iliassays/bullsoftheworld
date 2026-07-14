"""Onboard company logos. Neither market's provider hosts one directly, so we hop to each
company's own website (DSE's "Web Address" field; audited issuer domains only for US, which has
no official website field) and cache its best icon (apple-touch-icon > declared
icon > og:image > favicon).

Bytes are stored in `company_logos` and served by the API; a missing/failed row falls back to a
monogram in the UI. `status` + `checked_at` let a re-run skip names looked at recently instead of
re-hitting dead sites. We only ever GET, and keep a row only when the response is a real image within
a size cap, then decode and normalize it to PNG — never stored executable markup.

    uv run python -m ingestion.logos backfill DSE   # fetch for every DSE symbol
    uv run python -m ingestion.logos backfill US    # fetch for every US symbol
    uv run python -m ingestion.logos daily DSE        # only symbols not checked within RECHECK_DAYS
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import ipaddress
import re
import socket
import warnings
from collections.abc import Iterable
from io import BytesIO
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image, UnidentifiedImageError
from selectolax.parser import HTMLParser
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.db import get_sessionmaker
from bulls.core.models import CompanyLogo, Symbol
from bulls.market_data import get_provider

RECHECK_DAYS = 30  # in daily mode, skip names already checked this recently
_CONCURRENCY = 8  # be polite to company sites / favicon service
_MIN_BYTES = 100
_MAX_BYTES = 1_000_000
_MAX_HTML_BYTES = 2_000_000
_MAX_REDIRECTS = 4
_MAX_IMAGE_DIMENSION = 4096
Image.MAX_IMAGE_PIXELS = _MAX_IMAGE_DIMENSION * _MAX_IMAGE_DIMENSION
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
# Direct, hand-verified logo images for marquee names whose own sites block cloud IPs and aren't in
# any favicon service (banks especially). Sourced from Wikimedia Commons (reachable from the server).
# Highest priority — tried before the site/favicon path. Add a line here for any specific company.
_LOGO_URLS: dict[str, str] = {
    "DUTCHBANGL": "https://upload.wikimedia.org/wikipedia/commons/1/16/Dutch-bangla-bank-ltd.svg",
    "IPDC": "https://upload.wikimedia.org/wikipedia/commons/2/2a/Logo_of_IPDC_Finance.svg",
    "UTTARABANK": "https://upload.wikimedia.org/wikipedia/commons/b/ba/Logo_of_Uttara_Bank.svg",
    "BERGERPBL": "https://upload.wikimedia.org/wikipedia/commons/3/31/Berger.png",
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
    """Fetch, decode and normalize one public raster image.

    Decoding with Pillow rejects HTML disguised as an image and strips active metadata. SVG is
    intentionally not accepted from third parties; the API should never serve stored executable
    markup under an image content type.
    """
    response = await _safe_get(client, url, max_bytes=_MAX_BYTES)
    if response is None or response[0] != 200:
        return None
    content, final_url = response[2], response[3]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as opened:
                if (
                    opened.width <= 0
                    or opened.height <= 0
                    or opened.width > _MAX_IMAGE_DIMENSION
                    or opened.height > _MAX_IMAGE_DIMENSION
                ):
                    return None
                opened.load()
                image = opened.convert("RGBA")
                image.thumbnail((512, 512))
                output = BytesIO()
                image.save(output, format="PNG", optimize=True)
                normalized = output.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        return None
    if not (_MIN_BYTES < len(normalized) <= _MAX_BYTES):
        return None
    return {
        "image": normalized,
        "content_type": "image/png",
        "source_url": final_url,
        "status": "ok",
    }


async def _is_public_url(url: str) -> bool:
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return False
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo,
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError:
        return False
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            return False
    return bool(infos)


async def _safe_get(
    client: httpx.AsyncClient, url: str, *, max_bytes: int
) -> tuple[int, dict[str, str], bytes, str] | None:
    """Bounded public-network GET with every redirect target revalidated."""
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        if not await _is_public_url(current):
            return None
        try:
            async with client.stream("GET", current, headers=_HDRS) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        return None
                    current = urljoin(str(response.url), location)
                    continue
                declared = int(response.headers.get("content-length") or 0)
                if declared > max_bytes:
                    return None
                chunks = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        return None
                    chunks.append(chunk)
                return (
                    response.status_code,
                    dict(response.headers),
                    b"".join(chunks),
                    str(response.url),
                )
        except (httpx.HTTPError, ValueError):
            return None
    return None


async def _fetch_one(client: httpx.AsyncClient, provider, market: str, code: str) -> dict:
    """Resolve one company's logo → an upsert row dict (image + status).

    Order: the company site's own declared icons, then a favicon service (which has icons cached for
    sites that block or time out on us). An override domain wins over the provider-resolved one.
    """
    row: dict = {
        "market": market,
        "code": code,
        "image": None,
        "content_type": None,
        "source_url": None,
    }
    # 0. A hand-curated logo image, if we have one (wins over everything).
    direct = _LOGO_URLS.get(code)
    if direct:
        got = await _download_image(client, direct)
        if got:
            row.update(got)
            return row

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
    home = await _safe_get(client, site, max_bytes=_MAX_HTML_BYTES)
    home_ok = home is not None and home[0] == 200
    if home_ok and home is not None:
        html = home[2].decode("utf-8", errors="replace")
        for icon in pick_icons(html, home[3])[:4]:
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


def _normalize_codes(codes: Iterable[str] | None) -> list[str] | None:
    if codes is None:
        return None
    return sorted({code.strip().upper() for code in codes if code.strip()})


async def collect(
    *, market: str, recheck_days: int, codes: Iterable[str] | None = None
) -> dict[str, int]:
    provider = get_provider(market)
    requested = _normalize_codes(codes)
    sm = get_sessionmaker()
    async with sm() as session:
        code_stmt = select(Symbol.code).where(Symbol.market == market)
        if requested is not None:
            code_stmt = code_stmt.where(Symbol.code.in_(requested))
        selected_codes = list(await session.scalars(code_stmt.order_by(Symbol.code)))
        cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=recheck_days)
        # Only skip names we already have a logo for — so re-runs keep retrying the failures.
        recent = set(
            await session.scalars(
                select(CompanyLogo.code).where(
                    CompanyLogo.market == market,
                    CompanyLogo.status == "ok",
                    CompanyLogo.checked_at >= cutoff,
                )
            )
        )
    todo = [c for c in selected_codes if c not in recent]
    stats = {
        "requested": len(requested) if requested is not None else len(selected_codes),
        "missing": len(set(requested or ()) - set(selected_codes)),
        "total": len(selected_codes),
        "checked": 0,
        "ok": 0,
        "no_site": 0,
        "no_icon": 0,
        "error": 0,
    }
    sem = asyncio.Semaphore(_CONCURRENCY)

    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:

        async def worker(code: str) -> dict:
            async with sem:
                return await _fetch_one(client, provider, market, code)

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


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch bounded company-logo assets")
    parser.add_argument("mode", nargs="?", default="daily", choices=("daily", "backfill"))
    parser.add_argument("market", nargs="?", default="DSE")
    parser.add_argument("--codes", help="comma-separated symbol codes")
    return parser.parse_args(argv)


def main() -> None:
    args = _args()
    market = args.market.upper()
    recheck = 0 if args.mode == "backfill" else RECHECK_DAYS
    codes = args.codes.split(",") if args.codes else None
    print(
        f"[logos] {args.mode} {market}: fetching company logos "
        f"(recheck_days={recheck}, targeted={codes is not None})"
    )
    stats = asyncio.run(collect(market=market, recheck_days=recheck, codes=codes))
    print(f"[logos] done: {stats}")


if __name__ == "__main__":
    main()
