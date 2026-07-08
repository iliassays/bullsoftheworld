"""Ticker-scoped research brief: exact facts + cited evidence.

This is the first "Ask This Stock" slice. It deliberately keeps exact numbers in SQL and uses
retrieval over existing source tables for evidence. Embedding/vector search can replace the
ranking layer later without changing the response contract.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from api.deps import CurrentTenant, DbSession
from api.routers.buzz import gather_buzz
from bulls.ai.retrieval import retrieve
from bulls.core.models import (
    Announcement,
    Cashtag,
    Post,
    QuoteSnapshot,
    SignalEvent,
    Symbol,
    TickerAnalytics,
)

router = APIRouter(tags=["research"])
log = logging.getLogger(__name__)

EvidenceQuality = Literal["strong", "mixed", "weak"]
Reliability = Literal["official", "market", "system", "crowd"]

_ADVICE_RE = re.compile(
    r"\b(should\s+i|should\s+we|buy|sell|hold|target|entry|exit|stop\s*loss|"
    r"take\s+profit|portfolio\s+allocation|guaranteed|will\s+it\s+go)\b",
    re.I,
)
_MATERIAL_CATEGORIES = (
    "dividend",
    "earnings",
    "board_meeting",
    "rating",
    "halt",
    "corporate_action",
    "insider",
    "psi",
)
_MOVING_CATALYST_DAYS = 14


class ResearchSource(BaseModel):
    type: str
    id: str
    title: str
    date: str | None = None
    snippet: str
    reliability: Reliability


class ResearchInsight(BaseModel):
    lens: Literal["valuation", "technical", "liquidity", "ownership", "disclosure", "crowd"]
    stance: Literal["constructive", "watch", "risk", "unknown"]
    title: str
    detail: str
    evidence: str


class ResearchBriefResponse(BaseModel):
    code: str
    question: str
    answer: str
    evidence_quality: EvidenceQuality
    official_catalyst: bool
    blocked_advice: bool
    as_of: str
    facts: list[str]
    insights: list[ResearchInsight]
    sources: list[ResearchSource]


def _intent(question: str) -> str:
    q = question.lower()
    if any(w in q for w in ("dividend", "bonus", "record date", "cash")):
        return "dividend"
    if any(w in q for w in ("earnings", "eps", "profit", "loss", "financial")):
        return "earnings"
    if any(w in q for w in ("red flag", "risk", "worry", "bad news", "concern")):
        return "red_flags"
    if any(w in q for w in ("crowd", "people", "discussion", "talking", "sentiment", "hype")):
        return "crowd"
    if any(w in q for w in ("move", "moving", "up", "down", "why", "volume")):
        return "why_moving"
    if any(w in q for w in ("latest", "news", "announcement", "recent", "official", "dse")):
        return "latest_news"
    return "general"


def _snippet(text: str | None, *, limit: int = 260) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "..."


def _source_score(source: ResearchSource, question: str) -> int:
    q = question.lower()
    text = f"{source.title} {source.snippet}".lower()
    score = {"official": 40, "market": 30, "system": 25, "crowd": 10}[source.reliability]
    age = _source_age_days(source)
    if age is not None:
        if age <= 7:
            score += 20
        elif age <= 30:
            score += 12
        elif age <= 90:
            score += 5
    for token in re.findall(r"[a-z0-9]{3,}", q):
        if token in text:
            score += 8
    return score


def _source_date(source: ResearchSource) -> dt.date | None:
    if not source.date:
        return None
    try:
        return dt.date.fromisoformat(source.date[:10])
    except ValueError:
        return None


def _source_age_days(source: ResearchSource) -> int | None:
    day = _source_date(source)
    if day is None:
        return None
    return (dt.datetime.now(dt.UTC).date() - day).days


def _is_recent_official(source: ResearchSource, *, intent: str) -> bool:
    if source.reliability != "official":
        return False
    if intent != "why_moving":
        return True
    age = _source_age_days(source)
    return age is not None and 0 <= age <= _MOVING_CATALYST_DAYS


def _quality(
    sources: list[ResearchSource], official_catalyst: bool, *, intent: str
) -> EvidenceQuality:
    if intent == "crowd":
        return "mixed" if any(s.reliability == "crowd" for s in sources) else "weak"
    if intent == "red_flags" and not sources:
        return "weak"
    has_current_context = any(
        (s.reliability in ("system", "crowd") and (_source_age_days(s) or 9999) <= 7)
        for s in sources
    )
    if official_catalyst and (len(sources) >= 2 or intent != "why_moving"):
        return "strong"
    if intent == "why_moving" and has_current_context:
        return "mixed"
    if official_catalyst or any(s.reliability in ("market", "system") for s in sources):
        return "mixed"
    return "weak"


def _is_routine_notice(source: ResearchSource) -> bool:
    text = f"{source.title} {source.snippet}".lower()
    return any(
        x in text
        for x in (
            "record date",
            "resumption after record",
            "suspension for record",
            "agm date",
            "spot market",
        )
    )


def _is_risk_source(source: ResearchSource) -> bool:
    text = f"{source.title} {source.snippet}".lower()
    if source.reliability == "system":
        return any(x in text for x in ("overbought", "unusual volume", "selling", "breakdown"))
    if source.reliability == "official":
        if _is_routine_notice(source):
            return False
        return any(
            x in text
            for x in (
                "downgrade",
                "loss",
                "decrease",
                "decline",
                "halt",
                "suspension",
                "psi",
                "insider",
                "earnings",
                "financials",
            )
        )
    return source.reliability == "crowd"


def _rank_sources(
    sources: list[ResearchSource], *, question: str, intent: str
) -> list[ResearchSource]:
    if intent in ("latest_news", "dividend", "earnings"):
        # News questions are date-led. Vector similarity must not surface a stale AGM notice above
        # the newest material DSE filing.
        filtered = [s for s in sources if s.reliability == "official"]
        return sorted(
            filtered,
            key=lambda s: (_source_date(s) or dt.date.min, _source_score(s, question)),
            reverse=True,
        )
    if intent == "crowd":
        return sorted(
            [s for s in sources if s.reliability == "crowd"],
            key=lambda s: (_source_date(s) or dt.date.min, _source_score(s, question)),
            reverse=True,
        )
    if intent == "red_flags":
        filtered = [s for s in sources if _is_risk_source(s)]
        return sorted(filtered, key=lambda s: _source_score(s, question), reverse=True)
    return sorted(sources, key=lambda s: _source_score(s, question), reverse=True)


def _facts(
    *,
    code: str,
    quote: QuoteSnapshot | None,
    analytics: TickerAnalytics | None,
    posts_24h: int,
    chatter_x: float | None,
) -> list[str]:
    facts: list[str] = []
    if quote:
        delayed = " delayed" if quote.is_delayed else ""
        facts.append(
            f"${code} last traded at ৳{quote.ltp:g} ({quote.change_pct:+.2f}% today,"
            f" volume {quote.volume:,},{delayed} as of {quote.as_of.isoformat()})."
        )
    if analytics and analytics.relative_volume is not None:
        facts.append(f"Volume is {analytics.relative_volume:.1f}x its 20-session average.")
    if analytics and analytics.rsi_14 is not None:
        facts.append(f"RSI(14) is {analytics.rsi_14:.0f}.")
    if analytics and analytics.pe_ratio is not None:
        bits = [f"P/E is {analytics.pe_ratio:.1f}"]
        if analytics.pe_vs_sector is not None:
            bits.append(f"{analytics.pe_vs_sector:.2f}x sector median")
        facts.append(", ".join(bits) + ".")
    if posts_24h:
        extra = f", about {chatter_x:g}x baseline" if chatter_x else ""
        facts.append(f"Platform discussion: {posts_24h} posts in the last 24h{extra}.")
    return facts


def _fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0f}%"


def _fmt_x(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}x"


def _build_insights(
    *,
    analytics: TickerAnalytics | None,
    sources: list[ResearchSource],
    posts_24h: int,
    chatter_x: float | None,
) -> list[ResearchInsight]:
    insights: list[ResearchInsight] = []
    if analytics is None:
        return [
            ResearchInsight(
                lens="valuation",
                stance="unknown",
                title="Financial snapshot unavailable",
                detail="The deeper read needs the latest analytics row; this symbol has no usable snapshot yet.",
                evidence="Ticker analytics missing",
            )
        ]

    if analytics.pe_vs_sector is not None or analytics.pe_ratio is not None:
        if analytics.pe_vs_sector is not None and analytics.pe_vs_sector <= 0.8:
            stance = "constructive"
            title = "Valuation looks cheaper than sector"
            detail = "The market is pricing earnings below the sector median, so the next question is whether earnings quality and governance justify the discount."
        elif analytics.pe_vs_sector is not None and analytics.pe_vs_sector >= 1.25:
            stance = "risk"
            title = "Valuation asks for stronger proof"
            detail = "The stock trades at a premium to the sector median, so weak earnings or stale catalysts matter more."
        else:
            stance = "watch"
            title = "Valuation is not the main signal"
            detail = "The valuation read is near the sector zone; price action and disclosures may explain more than multiples."
        insights.append(
            ResearchInsight(
                lens="valuation",
                stance=stance,
                title=title,
                detail=detail,
                evidence=f"P/E {_fmt_x(analytics.pe_ratio)} · sector relative {_fmt_x(analytics.pe_vs_sector)}",
            )
        )

    if analytics.rsi_14 is not None or analytics.relative_volume is not None:
        hot = analytics.rsi_14 is not None and analytics.rsi_14 >= 70
        cold = analytics.rsi_14 is not None and analytics.rsi_14 <= 30
        high_volume = analytics.relative_volume is not None and analytics.relative_volume >= 1.5
        if hot and high_volume:
            stance = "risk"
            title = "Short-term move is crowded"
            detail = "High RSI plus elevated volume often means attention is already in the price; chasing risk is higher unless fresh official news confirms the move."
        elif cold:
            stance = "watch"
            title = "Oversold zone needs confirmation"
            detail = "RSI is low, but oversold alone is not a catalyst. Look for stabilization, volume, or an official event."
        elif high_volume:
            stance = "watch"
            title = "Volume is the live signal"
            detail = "Turnover is meaningfully above normal, so the move deserves review even if the official catalyst is not obvious."
        else:
            stance = "constructive"
            title = "Technical pressure is moderate"
            detail = "The short-term setup is not showing an extreme RSI or abnormal volume warning."
        insights.append(
            ResearchInsight(
                lens="technical",
                stance=stance,
                title=title,
                detail=detail,
                evidence=f"RSI {_fmt_pct(analytics.rsi_14)} · volume {analytics.relative_volume or 0:.1f}x 20-day average",
            )
        )

    flow_bits: list[str] = []
    if analytics.cmf_20 is not None:
        flow_bits.append(f"CMF {analytics.cmf_20:.2f}")
    if analytics.obv_slope is not None:
        flow_bits.append(f"OBV slope {analytics.obv_slope:.2f}")
    if flow_bits:
        positive = (analytics.cmf_20 or 0) > 0 and (analytics.obv_slope or 0) > 0
        negative = (analytics.cmf_20 or 0) < 0 and (analytics.obv_slope or 0) < 0
        insights.append(
            ResearchInsight(
                lens="liquidity",
                stance="constructive" if positive else "risk" if negative else "watch",
                title=(
                    "Accumulation signals align"
                    if positive
                    else "Distribution pressure is visible"
                    if negative
                    else "Flow signals are mixed"
                ),
                detail="Volume-flow indicators help separate simple price movement from buying or selling pressure, but they are still descriptive signals.",
                evidence=" · ".join(flow_bits),
            )
        )

    ownership_bits: list[str] = []
    if analytics.institute_delta is not None:
        ownership_bits.append(f"institute {analytics.institute_delta:+.2f} pp")
    if analytics.foreign_delta is not None:
        ownership_bits.append(f"foreign {analytics.foreign_delta:+.2f} pp")
    if ownership_bits:
        delta = (analytics.institute_delta or 0) + (analytics.foreign_delta or 0)
        insights.append(
            ResearchInsight(
                lens="ownership",
                stance="constructive" if delta > 0 else "risk" if delta < 0 else "watch",
                title=(
                    "Institutional ownership improved"
                    if delta > 0
                    else "Institutional ownership softened"
                    if delta < 0
                    else "Ownership is stable"
                ),
                detail="Ownership change is a slow signal; it can confirm or challenge a price move but should not override disclosures.",
                evidence=" · ".join(ownership_bits),
            )
        )

    official = [s for s in sources if s.reliability == "official"]
    if official:
        latest = official[0]
        insights.append(
            ResearchInsight(
                lens="disclosure",
                stance="watch",
                title="Official disclosure anchors the read",
                detail="The narrative should start from the newest material DSE filing, then compare price and volume behavior around it.",
                evidence=f"{latest.title} ({latest.date or 'date unavailable'})",
            )
        )
    else:
        insights.append(
            ResearchInsight(
                lens="disclosure",
                stance="risk",
                title="No official source in this answer",
                detail="Without a recent official item, the move is more likely driven by market mechanics, technicals, or discussion.",
                evidence="No ranked official announcement",
            )
        )

    if posts_24h or chatter_x:
        insights.append(
            ResearchInsight(
                lens="crowd",
                stance="watch",
                title="Crowd attention is measurable",
                detail="Discussion can explain attention, but it is weaker evidence than filings or market data.",
                evidence=f"{posts_24h} posts in 24h" + (f" · {chatter_x:g}x baseline" if chatter_x else ""),
            )
        )

    return insights[:6]


def _render_answer(
    *,
    code: str,
    question: str,
    intent: str,
    facts: list[str],
    sources: list[ResearchSource],
    official_catalyst: bool,
    evidence_quality: EvidenceQuality,
    blocked_advice: bool,
) -> str:
    lead = ""
    if blocked_advice:
        lead = (
            "I cannot tell you whether to buy, sell, hold, or set a target. "
            "I can summarize the evidence available right now. "
        )

    official = [s for s in sources if s.reliability == "official"]
    recent_official = [s for s in official if _is_recent_official(s, intent=intent)]
    crowd = [s for s in sources if s.reliability == "crowd"]
    system = [s for s in sources if s.reliability == "system"]

    fact_line = " ".join(facts[:3])
    if intent == "why_moving":
        if official_catalyst:
            catalyst = recent_official[0]
            body = (
                f"Bottom line: the move has a recent official source to review. {fact_line} "
                f"Most relevant official item: {catalyst.title} "
                f"({catalyst.date or 'date unavailable'})."
            )
        else:
            context = ""
            if official:
                context = (
                    f" Older official context exists, led by {official[0].title} "
                    f"({official[0].date or 'date unavailable'}), but it is not recent enough "
                    "to treat as today's catalyst."
                )
            body = (
                f"Bottom line: I do not see a recent official DSE catalyst for this move. "
                f"{fact_line} Treat this as price/volume or discussion-led until fresh official "
                f"news appears.{context}"
            )
    elif intent in ("dividend", "earnings", "latest_news"):
        if official:
            body = (
                f"Bottom line: the official record has a relevant item. {fact_line} "
                f"Latest relevant official item: {official[0].title}."
            )
        else:
            body = f"Bottom line: I did not find a matching recent official announcement. {fact_line}"
    elif intent == "crowd":
        if crowd:
            body = f"Bottom line: recent crowd context exists. {fact_line} Example: {crowd[0].snippet}"
        else:
            body = f"Bottom line: I did not find recent published platform discussion for ${code}. {fact_line}"
    elif intent == "red_flags":
        if official or system:
            top = (official + system)[0]
            body = f"Bottom line: review the cited evidence before forming a view. {fact_line} Main item: {top.title}."
        else:
            body = f"Bottom line: I did not find a recent official or system red-flag source. {fact_line}"
    else:
        if sources:
            body = f"Bottom line: the best available evidence is source-backed. {fact_line} Most relevant source: {sources[0].title}."
        else:
            body = f"Bottom line: I do not have enough retrieved evidence for a fuller brief. {fact_line}"

    suffix = f" Evidence quality: {evidence_quality}. This is evidence, not a trade call."
    return (lead + body + suffix).strip()


async def _announcement_sources(session, market: str, code: str, intent: str) -> list[ResearchSource]:
    categories = _MATERIAL_CATEGORIES
    if intent == "dividend":
        categories = ("dividend", "board_meeting", "corporate_action")
    elif intent == "earnings":
        categories = ("earnings", "board_meeting")
    elif intent == "red_flags":
        categories = ("halt", "rating", "insider", "psi", "earnings")

    rows = list(
        await session.scalars(
            select(Announcement)
            .where(
                Announcement.market == market,
                Announcement.code == code,
                Announcement.category.in_(categories),
            )
            .order_by(Announcement.published_at.desc(), Announcement.strength.desc())
            .limit(8)
        )
    )
    return [
        ResearchSource(
            type="announcement",
            id=str(a.id),
            title=f"{a.category.replace('_', ' ').title()}: {a.headline}",
            date=str(a.published_at),
            snippet=_snippet(a.body or a.headline),
            reliability="official",
        )
        for a in rows
    ]


async def _post_sources(session, market: str, code: str) -> list[ResearchSource]:
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=7)
    tagged = select(Cashtag.post_id).where(Cashtag.market == market, Cashtag.code == code)
    rows = list(
        await session.scalars(
            select(Post)
            .where(
                Post.id.in_(tagged),
                Post.created_at >= since,
                Post.moderation_status == "published",
                Post.kind == "user",
            )
            .order_by(Post.created_at.desc())
            .limit(6)
        )
    )
    return [
        ResearchSource(
            type="post",
            id=str(p.id),
            title=f"Recent platform post ({p.sentiment or 'neutral'})",
            date=p.created_at.isoformat(),
            snippet=_snippet(p.body),
            reliability="crowd",
        )
        for p in rows
    ]


async def _signal_sources(session, market: str, code: str) -> list[ResearchSource]:
    rows = list(
        await session.scalars(
            select(SignalEvent)
            .where(SignalEvent.market == market, SignalEvent.code == code)
            .order_by(SignalEvent.created_at.desc())
            .limit(4)
        )
    )
    return [
        ResearchSource(
            type="signal",
            id=str(s.id),
            title=f"{s.agent}: {s.event_type.replace('_', ' ')}",
            date=str(s.as_of_date) if s.as_of_date else s.created_at.isoformat(),
            snippet=f"Occurrence {s.occurrence_key}",
            reliability="system",
        )
        for s in rows
    ]


async def _vector_sources(session, market: str, code: str, question: str) -> list[ResearchSource]:
    try:
        chunks = await retrieve(session, question, market=market, code=code, k=8)
    except Exception as e:
        # Vector search is an enhancement. During rollout/backfills/model outages, the research
        # endpoint must still answer from direct SQL evidence.
        log.info("vector retrieval skipped for %s:%s: %s", market, code, e)
        return []
    return [
        ResearchSource(
            type=c.source_type,
            id=c.source_id,
            title=c.title,
            date=c.source_date,
            snippet=_snippet(c.text),
            reliability=c.reliability,
        )
        for c in chunks
    ]


def _dedupe_sources(sources: list[ResearchSource]) -> list[ResearchSource]:
    seen: set[tuple[str, str]] = set()
    out: list[ResearchSource] = []
    for s in sources:
        key = (s.type, s.id)
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


@router.get("/symbols/{code}/research")
async def research_brief(
    code: str,
    tenant: CurrentTenant,
    session: DbSession,
    q: str = Query("Why is this moving?", min_length=3, max_length=240),
) -> ResearchBriefResponse:
    code = code.upper()
    symbol = await session.get(Symbol, (tenant.market, code))
    if symbol is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")

    intent = _intent(q)
    quote = await session.get(QuoteSnapshot, (tenant.market, code))
    analytics = await session.get(TickerAnalytics, (tenant.market, code))
    buzz = await gather_buzz(session, tenant.market, code)

    facts = _facts(
        code=code,
        quote=quote,
        analytics=analytics,
        posts_24h=buzz.posts_24h,
        chatter_x=buzz.chatter_x,
    )
    vector_sources = await _vector_sources(session, tenant.market, code, q)
    announcement_sources = await _announcement_sources(session, tenant.market, code, intent)
    signal_sources = await _signal_sources(session, tenant.market, code)
    post_sources = await _post_sources(session, tenant.market, code)
    sources = [*vector_sources, *announcement_sources, *signal_sources, *post_sources]
    sources = _dedupe_sources(sources)
    sources = _rank_sources(sources, question=q, intent=intent)[:8]
    official_catalyst = intent != "crowd" and any(
        _is_recent_official(s, intent=intent) for s in sources
    )
    evidence_quality = _quality(sources, official_catalyst, intent=intent)
    insights = _build_insights(
        analytics=analytics,
        sources=sources,
        posts_24h=buzz.posts_24h,
        chatter_x=buzz.chatter_x,
    )
    blocked_advice = bool(_ADVICE_RE.search(q))
    answer = _render_answer(
        code=code,
        question=q,
        intent=intent,
        facts=facts,
        sources=sources,
        official_catalyst=official_catalyst,
        evidence_quality=evidence_quality,
        blocked_advice=blocked_advice,
    )
    return ResearchBriefResponse(
        code=code,
        question=q,
        answer=answer,
        evidence_quality=evidence_quality,
        official_catalyst=official_catalyst,
        blocked_advice=blocked_advice,
        as_of=dt.datetime.now(dt.UTC).isoformat(),
        facts=facts,
        insights=insights,
        sources=sources,
    )
