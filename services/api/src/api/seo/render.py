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
    noindex: bool = False,
    og_image: str = f"{SITE}/og.png",
    json_ld: list[dict] | None = None,
) -> str:
    """Assemble a complete, valid HTML document with all SEO head tags + hreflang alternates."""
    suffix = "" if path == "/" else path
    canonical = f"{SITE}/{lang}{suffix}"
    alts = "".join(
        f'<link rel="alternate" hreflang="{lg}" href="{SITE}/{lg}{suffix}">' for lg in LANGS
    )
    alts += f'<link rel="alternate" hreflang="x-default" href="{SITE}/bn{suffix}">'
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
        '<meta property="og:site_name" content="Bulls of Dhaka">'
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
        f'<p><a href="{canonical}">Open Bulls of Dhaka →</a></p>'
        "</body></html>"
    )


def _delayed_note(lang: str, as_of: dt.datetime) -> str:
    local = to_market_tz(as_of).strftime("%d %b %Y, %H:%M")
    return (
        f"১৫ মিনিট বিলম্বিত · সর্বশেষ {local} (ঢাকা)"
        if lang == "bn"
        else f"15-min delayed · as of {local} (Dhaka)"
    )


async def _render_stock(session: AsyncSession, market: str, lang: str, code: str) -> str | None:
    code = code.upper()
    sym = await session.get(Symbol, (market, code))
    if sym is None:
        return None
    quote = await session.get(QuoteSnapshot, (market, code))
    ta = await session.get(TickerAnalytics, (market, code))
    name = (sym.name_bn or sym.name_en) if lang == "bn" else sym.name_en
    sector = sym.sector
    price = f"৳{quote.ltp:g}" if quote else ""
    delayed = _delayed_note(lang, quote.as_of) if quote else ""

    if lang == "bn":
        title = f"{name} ({code}) শেয়ার দাম {price} — DSE | Bulls of Dhaka"
        desc = (
            f"{name}-এর সর্বশেষ শেয়ার দাম, ফান্ডামেন্টাল (P/E, EPS, মার্কেট ক্যাপ), চার্ট প্যাটার্ন ও খবর"
            + (f" · খাত: {sector}" if sector else "")
            + "। দাম ১৫ মিনিট বিলম্বিত। বিনিয়োগ পরামর্শ নয়।"
        )
        h1 = f"{name} ({code}) — শেয়ার দাম ও তথ্য"
    else:
        title = f"{name} ({code}) share price {price} — DSE | Bulls of Dhaka"
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
        if ta.market_cap_mn is not None:
            stats.append(("Market cap" if lang == "en" else "মার্কেট ক্যাপ", f"৳{ta.market_cap_mn / 10:,.0f} Cr"))
        if ta.dividend_yield is not None:
            stats.append(("Dividend yield" if lang == "en" else "ডিভিডেন্ড ইল্ড", f"{ta.dividend_yield:.1f}%"))
    stats_html = "".join(f"<li>{_e(k)}: {_e(v)}</li>" for k, v in stats)

    body = (
        f"<h1>{_e(h1)}</h1>"
        + (f'<p><strong>{_e(price)}</strong> <small>{_e(delayed)}</small></p>' if quote else "")
        + (f"<p>{_e('খাত' if lang == 'bn' else 'Sector')}: {_e(sector)}</p>" if sector else "")
        + (f"<ul>{stats_html}</ul>" if stats_html else "")
        + f"<p>{_e(desc)}</p>"
    )
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home" if lang == "en" else "হোম", "item": f"{SITE}/{lang}"},
            {"@type": "ListItem", "position": 2, "name": f"{name} ({code})", "item": f"{SITE}/{lang}/s/{code}"},
        ],
    }
    return _doc(lang=lang, path=f"/s/{code}", title=title, description=desc, body=body, json_ld=[breadcrumb])


async def _render_pattern_detail(lang: str, ptype: str) -> str | None:
    label = _PATTERN_TITLE.get(ptype)
    if not label:
        return None
    name = label[lang]
    if lang == "bn":
        title = f"{name} — DSE চার্ট প্যাটার্ন | Bulls of Dhaka"
        desc = f"{name} প্যাটার্ন কী, সাধারণত এরপর কী হয়, আর এখন কোন DSE শেয়ার এটি দেখাচ্ছে। প্রথাগত টেকনিক্যাল অ্যানালাইসিস, পরামর্শ নয়।"
    else:
        title = f"{name} — DSE chart pattern | Bulls of Dhaka"
        desc = f"What a {name.lower()} is, what usually happens next, and which DSE stocks show it now. Textbook technical analysis, not advice."
    body = f"<h1>{_e(name)}</h1><p>{_e(desc)}</p>"
    return _doc(lang=lang, path=f"/learn/patterns/{ptype}", title=title, description=desc, body=body)


def _static_page(lang: str, path: str) -> str:
    """Meta + a real heading/description for the non-stock indexable routes."""
    pages = {
        "/": {
            "bn": ("Bulls of Dhaka — ঢাকা স্টক এক্সচেঞ্জের তথ্য, গুজব নয়", "DSE-র শেয়ারের দাম, ফান্ডামেন্টাল, চার্ট প্যাটার্ন ও কমিউনিটি — এক জায়গায়। বর্ণনামূলক তথ্য, বিনিয়োগ পরামর্শ নয়।"),
            "en": ("Bulls of Dhaka — Dhaka Stock Exchange data, not rumours", "DSE share prices, fundamentals, chart patterns and community — in one place. Descriptive data, not investment advice."),
        },
        "/markets": {
            "bn": ("মার্কেট স্ক্রিন — DSE গেইনার, লুজার, ভলিউম, ভ্যালু | Bulls of Dhaka", "ঢাকা স্টক এক্সচেঞ্জের রেডিমেড স্ক্রিন: টপ গেইনার/লুজার, অস্বাভাবিক ভলিউম, সস্তা vs খাত, প্রাতিষ্ঠানিক প্রবাহ, চার্ট প্যাটার্ন।"),
            "en": ("Market screens — DSE gainers, losers, volume, value | Bulls of Dhaka", "Ready-made Dhaka Stock Exchange screens: top gainers/losers, unusual volume, cheap-vs-sector, institutional flow, chart patterns."),
        },
        "/learn/patterns": {
            "bn": ("চার্ট প্যাটার্ন — DSE শেয়ারে ত্রিভুজ, চ্যানেল, ডাবল টপ/বটম | Bulls of Dhaka", "ঢাকা স্টক এক্সচেঞ্জের শেয়ারে গঠিত হওয়া ক্লাসিক চার্ট প্যাটার্ন — প্রতিটির মানে ও এখন কোন শেয়ার দেখাচ্ছে। প্রথাগত টেকনিক্যাল অ্যানালাইসিস, পরামর্শ নয়।"),
            "en": ("Chart patterns — triangles, channels, double tops/bottoms on DSE | Bulls of Dhaka", "Classic chart patterns forming on Dhaka Stock Exchange stocks — what each means and which stocks show it now. Textbook technical analysis, not advice."),
        },
        "/ideas": {
            "bn": ("আইডিয়া — DSE স্ক্রিনার ও লেন্স | Bulls of Dhaka", "ঢাকা স্টক এক্সচেঞ্জের জন্য কিউরেটেড আইডিয়া বোর্ড ও ইনভেস্টর লেন্স। বর্ণনামূলক তথ্য, পরামর্শ নয়।"),
            "en": ("Ideas — DSE screeners & lenses | Bulls of Dhaka", "Curated idea boards and investor lenses for the Dhaka Stock Exchange. Descriptive data, not advice."),
        },
        "/about": {
            "bn": ("Bulls of Dhaka সম্পর্কে — DSE-র জন্য তথ্যভিত্তিক প্ল্যাটফর্ম", "Bulls of Dhaka কী, কেন 'তথ্যে চলুন, গুজবে নয়', আর কোন কোন অটোমেটেড ডেস্ক DSE-র ডেটা তুলে ধরে।"),
            "en": ("About Bulls of Dhaka — a facts-first platform for the DSE", "What Bulls of Dhaka is, why 'facts, not rumours', and the automated desks that surface Dhaka Stock Exchange data."),
        },
    }
    title, desc = pages[path][lang]
    json_ld = None
    if path == "/":
        json_ld = [
            {"@context": "https://schema.org", "@type": "Organization", "name": "Bulls of Dhaka", "url": SITE, "logo": f"{SITE}/logo-mark-v2.png"},
            {"@context": "https://schema.org", "@type": "WebSite", "name": "Bulls of Dhaka", "url": SITE,
             "potentialAction": {"@type": "SearchAction", "target": f"{SITE}/bn/s/{{search_term_string}}", "query-input": "required name=search_term_string"}},
        ]
    return _doc(lang=lang, path=path, title=title, description=desc, body=f"<h1>{_e(title)}</h1><p>{_e(desc)}</p>", json_ld=json_ld)


async def render_path(session: AsyncSession, market: str, raw_path: str) -> tuple[str, int]:
    """Render the HTML for an SPA path (already stripped of any /seo prefix). Returns (html, status).

    Unknown/private paths render a valid noindex page rather than erroring — the CloudFront rule
    only routes bots here, and robots.txt already disallows the private ones, so this is a safety net.
    """
    parts = [p for p in raw_path.strip("/").split("/") if p]
    lang = parts[0] if parts and parts[0] in LANGS else "bn"
    rest = parts[1:] if parts and parts[0] in LANGS else parts

    # /{lang}  (home)
    if not rest:
        return _static_page(lang, "/"), 200
    if rest == ["markets"]:
        return _static_page(lang, "/markets"), 200
    if rest == ["ideas"]:
        return _static_page(lang, "/ideas"), 200
    if rest == ["about"]:
        return _static_page(lang, "/about"), 200
    if rest == ["learn", "patterns"]:
        return _static_page(lang, "/learn/patterns"), 200
    if len(rest) == 3 and rest[0] == "learn" and rest[1] == "patterns":
        page = await _render_pattern_detail(lang, rest[2])
        return (page, 200) if page else (_static_page(lang, "/learn/patterns"), 200)
    if len(rest) == 2 and rest[0] == "s":
        page = await _render_stock(session, market, lang, rest[1])
        if page:
            return page, 200
        # Unknown ticker → a minimal noindex 404-ish page.
        title = "Not found — Bulls of Dhaka" if lang == "en" else "পাওয়া যায়নি — Bulls of Dhaka"
        return _doc(lang=lang, path="/", title=title, description=title, body=f"<h1>{_e(title)}</h1>", noindex=True), 404

    # Anything else (private/unknown): valid but noindex.
    title = "Bulls of Dhaka"
    return _doc(lang=lang, path="/", title=title, description=title, body=f"<h1>{_e(title)}</h1>", noindex=True), 200
