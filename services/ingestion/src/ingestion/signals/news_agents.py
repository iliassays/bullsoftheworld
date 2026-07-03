"""News-triggered agents: post a desk-note when a material dividend / earnings / rating lands.

Reads the classified `announcements` table (populated by ingestion.news), so detection is just
"a new high-strength announcement in my category that I haven't posted yet". Dedup is exact, per
announcement (its content-hash key). Fact (the disclosure) + a plain "what it means", no advice.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from bulls.core.db import get_sessionmaker
from bulls.core.models import Announcement, SignalEvent
from ingestion.signals.agents import AGENTS, ensure_agents
from ingestion.signals.publish import publish_note

# announcement category -> agent beat
_BEATS = {"dividend": "dividend", "earnings": "earnings", "rating": "rating"}
_STRENGTH_FLOOR = 50  # only post items worth a user's attention
_RECENT_DAYS = 30  # don't post stale history on first run / backfill

# beat -> (EN framing, BN framing). The headline carries the fact; we add the "what it means".
_TEMPLATES: dict[str, tuple[str, str]] = {
    "dividend": (
        "Dividend update — {headline}. A dividend returns cash to holders; check the record date "
        "for eligibility. Not advice.",
        "ডিভিডেন্ড আপডেট — {headline}. ডিভিডেন্ড শেয়ারহোল্ডারদের নগদ ফেরত দেয়; যোগ্যতার জন্য রেকর্ড "
        "ডেট দেখুন। পরামর্শ নয়।",
    ),
    "earnings": (
        "Results update — {headline}. Earnings drive valuation over time; see the Fundamentals tab. "
        "Descriptive, not advice.",
        "ফলাফল আপডেট — {headline}. আয় দীর্ঘমেয়াদে মূল্যায়ন নির্ধারণ করে; ফান্ডামেন্টাল ট্যাব দেখুন। "
        "তথ্যমূলক, পরামর্শ নয়।",
    ),
    "rating": (
        "Credit rating update — {headline}. A rating reflects assessed creditworthiness. "
        "Descriptive, not advice.",
        "ক্রেডিট রেটিং আপডেট — {headline}. রেটিং মূল্যায়িত ঋণযোগ্যতা প্রতিফলিত করে। তথ্যমূলক, পরামর্শ নয়।",
    ),
}


def _decoded_fact(category: str, details: dict | None, locale: str) -> str | None:
    """The decoded numbers as one readable clause — the note leads with these, not the raw
    headline. Omit-over-mislead: any missing field simply drops out; no decode → None."""
    d = details or {}
    bn = locale == "bn"
    if category == "earnings" and d.get("eps_current") is not None:
        cur = d["eps_current"]
        period = f"{d['period']} " if d.get("period") else ""
        fact = f"{period}EPS ৳{cur:g}"
        prior = d.get("eps_prior")
        if prior is not None:
            fact += f" (আগের বছর ৳{prior:g})" if bn else f" vs ৳{prior:g} a year earlier"
            if prior > 0:
                pct = (cur - prior) / prior * 100
                fact += f" ({pct:+.0f}%)"
        if d.get("nav") is not None:
            fact += f"; NAV ৳{d['nav']:g}"
        return fact
    if category == "dividend":
        if d.get("no_dividend"):
            return "এ বছরের জন্য কোনো লভ্যাংশ ঘোষণা হয়নি" if bn else "no dividend declared"
        parts = []
        if d.get("cash_pct") is not None:
            parts.append(f"{d['cash_pct']:g}% {'নগদ' if bn else 'cash'}")
        if d.get("stock_pct") is not None:
            parts.append(f"{d['stock_pct']:g}% {'স্টক' if bn else 'stock'}")
        if not parts:
            return None
        fact = " + ".join(parts) + (" লভ্যাংশ ঘোষণা" if bn else " dividend declared")
        if d.get("record_date"):
            fact += f"; {'রেকর্ড ডেট' if bn else 'record date'} {d['record_date']}"
        return fact
    if category == "rating":
        parts = []
        if d.get("long_term"):
            parts.append(f"{d['long_term']} ({'দীর্ঘমেয়াদি' if bn else 'long-term'})")
        if d.get("short_term"):
            parts.append(f"{d['short_term']} ({'স্বল্পমেয়াদি' if bn else 'short-term'})")
        if not parts:
            return None
        return ("রেটিং: " if bn else "rated ") + ", ".join(parts)
    return None


def render(category: str, headline: str, code: str, locale: str, details: dict | None = None) -> str:
    en, bn = _TEMPLATES[category]
    tmpl = bn if locale == "bn" else en
    # Decoded numbers beat the raw exchange headline; the headline is the fallback only.
    fact = _decoded_fact(category, details, locale)
    return f"{code} — " + tmpl.format(headline=fact or headline)


async def run_news_agents(
    market: str, *, tenant_id: str = "bullsofdhaka"
) -> dict[str, int]:
    """Post one note per new material dividend/earnings/rating announcement."""
    since = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=_RECENT_DAYS)
    sm = get_sessionmaker()
    published = 0
    async with sm() as session:
        ids = await ensure_agents(session, tenant_id)
        anns = list(
            await session.scalars(
                select(Announcement).where(
                    Announcement.market == market,
                    Announcement.category.in_(list(_BEATS)),
                    Announcement.strength >= _STRENGTH_FLOOR,
                    Announcement.published_at >= since,
                )
            )
        )
        for a in anns:
            event_type = f"news_{a.category}"
            # exact-key dedup: one note per announcement, ever
            seen = await session.scalar(
                select(SignalEvent.id).where(
                    SignalEvent.market == market,
                    SignalEvent.code == a.code,
                    SignalEvent.event_type == event_type,
                    SignalEvent.occurrence_key == a.key,
                )
            )
            if seen:
                continue
            beat = _BEATS[a.category]
            await publish_note(
                session,
                tenant_id=tenant_id,
                market=market,
                code=a.code,
                agent_id=ids[beat],
                agent_handle=AGENTS[beat][0],
                event_type=event_type,
                occurrence_key=a.key,
                body_i18n={
                    "bn": render(a.category, a.headline, a.code, "bn", a.details),
                    "en": render(a.category, a.headline, a.code, "en", a.details),
                },
                as_of=a.published_at,
            )
            published += 1
        await session.commit()
    return {"announcements": len(anns), "published": published}
