"""Server-rendered HTML for crawlers and social scrapers.

The site is a client-rendered SPA on static hosting, so search engines (unreliably) and social
scrapers (never) run its JS — every shared link would otherwise show one generic card. A
CloudFront Function routes bot/social user-agents here (/seo/<the original path>); humans keep
getting the SPA from S3. This module renders a real HTML document per route: correct title,
description, canonical, hreflang, Open Graph/Twitter, JSON-LD, and genuine above-the-fold content.

Honesty (CLAUDE.md #4): any price shown here carries its as_of + a delayed marker, exactly as the
live UI does — never fake freshness, even for a bot.

Not cloaking: the content mirrors what a human sees on the same route; it just doesn't require JS.
"""

from __future__ import annotations

import datetime as dt
import html
import json

from sqlalchemy.ext.asyncio import AsyncSession

from bulls.core.markets import format_money_millions, get_market_profile
from bulls.core.models import Symbol, TickerAnalytics
from bulls.core.models.quote import QuoteSnapshot
from bulls.market_data.calendar import to_market_tz

SITE = "https://bullsofdhaka.com"
LANGS = ("bn", "en")
_PATTERN_TITLE = {
    "ascending_triangle": {"bn": "ঊর্ধ্বমুখী ত্রিভুজ", "en": "Ascending Triangle"},
    "descending_triangle": {"bn": "নিম্নমুখী ত্রিভুজ", "en": "Descending Triangle"},
    "channel_up": {"bn": "ঊর্ধ্বমুখী চ্যানেল", "en": "Rising Channel"},
    "channel_down": {"bn": "নিম্নমুখী চ্যানেল", "en": "Falling Channel"},
    "channel_horizontal": {"bn": "আনুভূমিক চ্যানেল", "en": "Horizontal Channel"},
    "double_top": {"bn": "ডাবল টপ", "en": "Double Top"},
    "double_bottom": {"bn": "ডাবল বটম", "en": "Double Bottom"},
}


def _e(s: object) -> str:
    return html.escape(str(s), quote=True)


def _doc(
    *,
    lang: str,
    path: str,  # unprefixed app path, e.g. "/s/GP" or "/"
    title: str,
    description: str,
    body: str,
    site: str = SITE,
    brand: str = "Bulls of Dhaka",
    noindex: bool = False,
    og_image: str | None = None,
    json_ld: list[dict] | None = None,
) -> str:
    """Assemble a complete, valid HTML document with all SEO head tags + hreflang alternates."""
    og_image = og_image or f"{site}/og.png"
    suffix = "" if path == "/" else path
    canonical = f"{site}/{lang}{suffix}"
    alts = "".join(
        f'<link rel="alternate" hreflang="{lg}" href="{site}/{lg}{suffix}">' for lg in LANGS
    )
    alts += f'<link rel="alternate" hreflang="x-default" href="{site}/bn{suffix}">'
    robots = '<meta name="robots" content="noindex,follow">' if noindex else ""
    ld = "".join(
        f'<script type="application/ld+json">{json.dumps(b, ensure_ascii=False)}</script>'
        for b in (json_ld or [])
    )
    t, d = _e(title), _e(description)
    return (
        "<!doctype html>"
        f'<html lang="{lang}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{t}</title>"
        f'<meta name="description" content="{d}">'
        f'<link rel="canonical" href="{canonical}">{alts}{robots}'
        '<meta property="og:type" content="website">'
        f'<meta property="og:site_name" content="{_e(brand)}">'
        f'<meta property="og:title" content="{t}">'
        f'<meta property="og:description" content="{d}">'
        f'<meta property="og:url" content="{canonical}">'
        f'<meta property="og:image" content="{_e(og_image)}">'
        '<meta name="twitter:card" content="summary_large_image">'
        f'<meta name="twitter:title" content="{t}">'
        f'<meta name="twitter:description" content="{d}">'
        f'<meta name="twitter:image" content="{_e(og_image)}">'
        f"{ld}</head><body>{body}"
        # A link to the real app so a human who somehow lands here (and the crawl graph) can proceed.
        f'<p><a href="{canonical}">Open {_e(brand)} →</a></p>'
        "</body></html>"
    )


def _delayed_note(lang: str, as_of: dt.datetime, market: str) -> str:
    profile = get_market_profile(market)
    local = to_market_tz(as_of, market=market).strftime("%d %b %Y, %H:%M")
    place = profile.place_label(lang)
    return (
        f"১৫ মিনিট বিলম্বিত · সর্বশেষ {local} ({place})"
        if lang == "bn"
        else f"15-min delayed · as of {local} ({place})"
    )


def _market_cap_text(value_mn: float | None, market: str) -> str | None:
    if value_mn is None:
        return None
    return format_money_millions(value_mn, market, style="market_cap")


async def _render_stock(
    session: AsyncSession,
    market: str,
    lang: str,
    code: str,
    *,
    site: str = SITE,
    brand: str = "Bulls of Dhaka",
) -> str | None:
    code = code.upper()
    profile = get_market_profile(market)
    exchange = profile.exchange_label(lang)
    sym = await session.get(Symbol, (market, code))
    if sym is None:
        return None
    quote = await session.get(QuoteSnapshot, (market, code))
    ta = await session.get(TickerAnalytics, (market, code))
    name = (sym.name_bn or sym.name_en) if lang == "bn" else sym.name_en
    sector = sym.sector
    price = f"{profile.currency_symbol}{quote.ltp:g}" if quote else ""
    delayed = _delayed_note(lang, quote.as_of, market) if quote else ""

    if lang == "bn":
        title = f"{name} ({code}) শেয়ার দাম {price} — {exchange} | {brand}"
        desc = (
            f"{name}-এর সর্বশেষ শেয়ার দাম, ফান্ডামেন্টাল (P/E, EPS, মার্কেট ক্যাপ), চার্ট প্যাটার্ন ও খবর"
            + (f" · খাত: {sector}" if sector else "")
            + "। দাম ১৫ মিনিট বিলম্বিত। বিনিয়োগ পরামর্শ নয়।"
        )
        h1 = f"{name} ({code}) — শেয়ার দাম ও তথ্য"
    else:
        title = f"{name} ({code}) share price {price} — {profile.exchange_code} | {brand}"
        desc = (
            f"{name} latest share price, fundamentals (P/E, EPS, market cap), chart patterns and news"
            + (f" · Sector: {sector}" if sector else "")
            + ". Price 15-min delayed. Not investment advice."
        )
        h1 = f"{name} ({code}) — share price & data"

    stats = []
    if ta is not None:
        if ta.pe_ratio is not None:
            stats.append(("P/E", f"{ta.pe_ratio:.1f}"))
        cap = _market_cap_text(ta.market_cap_mn, market)
        if cap is not None:
            stats.append(("Market cap" if lang == "en" else "মার্কেট ক্যাপ", cap))
        if ta.dividend_yield is not None:
            stats.append(
                ("Dividend yield" if lang == "en" else "ডিভিডেন্ড ইল্ড", f"{ta.dividend_yield:.1f}%")
            )
    stats_html = "".join(f"<li>{_e(k)}: {_e(v)}</li>" for k, v in stats)

    body = (
        f"<h1>{_e(h1)}</h1>"
        + (f"<p><strong>{_e(price)}</strong> <small>{_e(delayed)}</small></p>" if quote else "")
        + (f"<p>{_e('খাত' if lang == 'bn' else 'Sector')}: {_e(sector)}</p>" if sector else "")
        + (f"<ul>{stats_html}</ul>" if stats_html else "")
        + f"<p>{_e(desc)}</p>"
    )
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home" if lang == "en" else "হোম",
                "item": f"{site}/{lang}",
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": f"{name} ({code})",
                "item": f"{site}/{lang}/s/{code}",
            },
        ],
    }
    return _doc(
        lang=lang,
        path=f"/s/{code}",
        title=title,
        description=desc,
        body=body,
        site=site,
        brand=brand,
        json_ld=[breadcrumb],
    )


async def _render_pattern_detail(
    lang: str,
    ptype: str,
    *,
    market: str = "DSE",
    site: str = SITE,
    brand: str = "Bulls of Dhaka",
) -> str | None:
    label = _PATTERN_TITLE.get(ptype)
    if not label:
        return None
    profile = get_market_profile(market)
    exchange = profile.exchange_label(lang)
    name = label[lang]
    if lang == "bn":
        title = f"{name} — {exchange} চার্ট প্যাটার্ন | {brand}"
        desc = f"{name} প্যাটার্ন কী, সাধারণত এরপর কী হয়, আর এখন কোন {exchange} শেয়ার এটি দেখাচ্ছে। প্রথাগত টেকনিক্যাল অ্যানালাইসিস, পরামর্শ নয়।"
    else:
        title = f"{name} — {profile.exchange_code} chart pattern | {brand}"
        desc = f"What a {name.lower()} is, what usually happens next, and which {profile.exchange_code} stocks show it now. Textbook technical analysis, not advice."
    body = f"<h1>{_e(name)}</h1><p>{_e(desc)}</p>"
    return _doc(
        lang=lang,
        path=f"/learn/patterns/{ptype}",
        title=title,
        description=desc,
        body=body,
        site=site,
        brand=brand,
    )


def _static_page(
    lang: str,
    path: str,
    *,
    market: str = "DSE",
    site: str = SITE,
    brand: str = "Bulls of Dhaka",
) -> str:
    """Meta + a real heading/description for the non-stock indexable routes."""
    profile = get_market_profile(market)
    exchange = profile.exchange_label(lang)
    exchange_name = profile.exchange_name_label(lang)
    pages = {
        "/": {
            "bn": (
                f"{brand} — {exchange_name}-এর তথ্য, গুজব নয়",
                f"{exchange}-র শেয়ারের দাম, ফান্ডামেন্টাল, চার্ট প্যাটার্ন ও কমিউনিটি — এক জায়গায়। বর্ণনামূলক তথ্য, বিনিয়োগ পরামর্শ নয়।",
            ),
            "en": (
                f"{brand} — {profile.exchange_name} data, not rumours",
                f"{profile.exchange_code} share prices, fundamentals, chart patterns and community — in one place. Descriptive data, not investment advice.",
            ),
        },
        "/markets": {
            "bn": (
                f"মার্কেট স্ক্রিন — {exchange} গেইনার, লুজার, ভলিউম, ভ্যালু | {brand}",
                f"{exchange_name}-এর রেডিমেড স্ক্রিন: টপ গেইনার/লুজার, অস্বাভাবিক ভলিউম, সস্তা vs খাত, প্রাতিষ্ঠানিক প্রবাহ, চার্ট প্যাটার্ন।",
            ),
            "en": (
                f"Market screens — {profile.exchange_code} gainers, losers, volume, value | {brand}",
                f"Ready-made {profile.exchange_name} screens: top gainers/losers, unusual volume, cheap-vs-sector, institutional flow, chart patterns.",
            ),
        },
        "/learn/patterns": {
            "bn": (
                f"চার্ট প্যাটার্ন — {exchange} শেয়ারে ত্রিভুজ, চ্যানেল, ডাবল টপ/বটম | {brand}",
                f"{exchange_name}-এর শেয়ারে গঠিত হওয়া ক্লাসিক চার্ট প্যাটার্ন — প্রতিটির মানে ও এখন কোন শেয়ার দেখাচ্ছে। প্রথাগত টেকনিক্যাল অ্যানালাইসিস, পরামর্শ নয়।",
            ),
            "en": (
                f"Chart patterns — triangles, channels, double tops/bottoms on {profile.exchange_code} | {brand}",
                f"Classic chart patterns forming on {profile.exchange_name} stocks — what each means and which stocks show it now. Textbook technical analysis, not advice.",
            ),
        },
        "/ideas": {
            "bn": (
                f"আইডিয়া — {exchange} স্ক্রিনার ও লেন্স | {brand}",
                f"{exchange_name}-এর জন্য কিউরেটেড আইডিয়া বোর্ড ও ইনভেস্টর লেন্স। বর্ণনামূলক তথ্য, পরামর্শ নয়।",
            ),
            "en": (
                f"Ideas — {profile.exchange_code} screeners & lenses | {brand}",
                f"Curated idea boards and investor lenses for {profile.exchange_name}. Descriptive data, not advice.",
            ),
        },
        "/about": {
            "bn": (
                f"{brand} সম্পর্কে — {exchange}-র জন্য তথ্যভিত্তিক প্ল্যাটফর্ম",
                f"{brand} কী, কেন 'তথ্যে চলুন, গুজবে নয়', আর কোন কোন অটোমেটেড ডেস্ক {exchange}-র ডেটা তুলে ধরে।",
            ),
            "en": (
                f"About {brand} — a facts-first platform for {profile.exchange_code}",
                f"What {brand} is, why 'facts, not rumours', and the automated desks that surface {profile.exchange_name} data.",
            ),
        },
    }
    title, desc = pages[path][lang]
    json_ld = None
    if path == "/":
        json_ld = [
            {
                "@context": "https://schema.org",
                "@type": "Organization",
                "name": brand,
                "url": site,
                "logo": f"{site}/logo-mark-v2.png",
            },
            {
                "@context": "https://schema.org",
                "@type": "WebSite",
                "name": brand,
                "url": site,
                "potentialAction": {
                    "@type": "SearchAction",
                    "target": f"{site}/bn/s/{{search_term_string}}",
                    "query-input": "required name=search_term_string",
                },
            },
        ]
    return _doc(
        lang=lang,
        path=path,
        title=title,
        description=desc,
        body=f"<h1>{_e(title)}</h1><p>{_e(desc)}</p>",
        site=site,
        brand=brand,
        json_ld=json_ld,
    )


async def render_path(
    session: AsyncSession,
    market: str,
    raw_path: str,
    *,
    site: str = SITE,
    brand: str = "Bulls of Dhaka",
) -> tuple[str, int]:
    """Render the HTML for an SPA path (already stripped of any /seo prefix). Returns (html, status).

    Unknown/private paths render a valid noindex page rather than erroring — the CloudFront rule
    only routes bots here, and robots.txt already disallows the private ones, so this is a safety net.
    """
    parts = [p for p in raw_path.strip("/").split("/") if p]
    lang = parts[0] if parts and parts[0] in LANGS else "bn"
    rest = parts[1:] if parts and parts[0] in LANGS else parts

    # /{lang}  (home)
    if not rest:
        return _static_page(lang, "/", market=market, site=site, brand=brand), 200
    if rest == ["markets"]:
        return _static_page(lang, "/markets", market=market, site=site, brand=brand), 200
    if rest == ["ideas"]:
        return _static_page(lang, "/ideas", market=market, site=site, brand=brand), 200
    if rest == ["about"]:
        return _static_page(lang, "/about", market=market, site=site, brand=brand), 200
    if rest == ["learn", "patterns"]:
        return _static_page(lang, "/learn/patterns", market=market, site=site, brand=brand), 200
    if len(rest) == 3 and rest[0] == "learn" and rest[1] == "patterns":
        page = await _render_pattern_detail(lang, rest[2], market=market, site=site, brand=brand)
        return (
            (page, 200)
            if page
            else (_static_page(lang, "/learn/patterns", market=market, site=site, brand=brand), 200)
        )
    if len(rest) == 2 and rest[0] == "s":
        page = await _render_stock(session, market, lang, rest[1], site=site, brand=brand)
        if page:
            return page, 200
        # Unknown ticker → a minimal noindex 404-ish page.
        title = f"Not found — {brand}" if lang == "en" else f"পাওয়া যায়নি — {brand}"
        return _doc(
            lang=lang,
            path="/",
            title=title,
            description=title,
            body=f"<h1>{_e(title)}</h1>",
            site=site,
            brand=brand,
            noindex=True,
        ), 404

    # Anything else (private/unknown): valid but noindex.
    title = brand
    return _doc(
        lang=lang,
        path="/",
        title=title,
        description=title,
        body=f"<h1>{_e(title)}</h1>",
        site=site,
        brand=brand,
        noindex=True,
    ), 200
