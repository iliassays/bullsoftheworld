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

from api.deps import CurrentTenant, DbSession, enforce_market_feature
from api.routers.buzz import gather_buzz
from api.routers.market import QuoteOut, load_freshest_quotes
from bulls.ai.retrieval import retrieve
from bulls.core.markets import get_market_profile
from bulls.core.models import (
    Announcement,
    Cashtag,
    InstitutionalHoldingSummary,
    Post,
    SecFiling,
    SecFinancialFact,
    SignalEvent,
    Symbol,
    TickerAnalytics,
)

router = APIRouter(tags=["research"])
log = logging.getLogger(__name__)

EvidenceQuality = Literal["strong", "mixed", "weak"]
Reliability = Literal["official", "market", "system", "crowd"]
Lang = Literal["en", "bn"]

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
_LANG_QUERY = Query("en")


class ResearchSource(BaseModel):
    type: str
    id: str
    title: str
    date: str | None = None
    snippet: str
    reliability: Reliability
    url: str | None = None


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
    if any(w in q for w in ("13f", "institution", "fund", "holding", "smart money")):
        return "institutional"
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
    if intent == "institutional":
        return sorted(
            [source for source in sources if source.type == "sec_13f"],
            key=lambda source: (
                _source_date(source) or dt.date.min,
                _source_score(source, question),
            ),
            reverse=True,
        )
    if intent in ("latest_news", "dividend", "earnings", "institutional"):
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


def _quality_label(evidence_quality: EvidenceQuality, lang: Lang) -> str:
    if lang == "bn":
        return {"strong": "ভাল", "mixed": "মিশ্র", "weak": "দুর্বল"}[evidence_quality]
    return {"strong": "good", "mixed": "mixed", "weak": "weak"}[evidence_quality]


def _facts(
    *,
    code: str,
    quote: QuoteOut | None,
    analytics: TickerAnalytics | None,
    posts_24h: int,
    chatter_x: float | None,
    lang: Lang = "en",
    market: str = "DSE",
) -> list[str]:
    facts: list[str] = []
    profile = get_market_profile(market)
    if quote:
        period_bn = "আজ" if profile.features.intraday_quotes else "সর্বশেষ সেশনে"
        period_en = "today" if profile.features.intraday_quotes else "in the latest session"
        if lang == "bn":
            delayed = " বিলম্বিত" if quote.is_delayed else ""
            facts.append(
                f"${code} সর্বশেষ {profile.currency_symbol}{quote.ltp:g} দরে ট্রেড করেছে "
                f"({quote.change_pct:+.2f}% {period_bn}, ভলিউম {quote.volume:,},"
                f"{delayed} সময় {quote.as_of.isoformat()})।"
            )
        else:
            delayed = " delayed" if quote.is_delayed else ""
            facts.append(
                f"${code} last traded at {profile.currency_symbol}{quote.ltp:g} "
                f"({quote.change_pct:+.2f}% {period_en},"
                f" volume {quote.volume:,},{delayed} as of {quote.as_of.isoformat()})."
            )
    if analytics and analytics.relative_volume is not None:
        facts.append(
            f"ভলিউম ২০ সেশনের গড়ের {analytics.relative_volume:.1f} গুণ।"
            if lang == "bn"
            else f"Volume is {analytics.relative_volume:.1f}x its 20-session average."
        )
    if analytics and analytics.rsi_14 is not None:
        facts.append(
            f"RSI(14) {analytics.rsi_14:.0f}।"
            if lang == "bn"
            else f"RSI(14) is {analytics.rsi_14:.0f}."
        )
    if analytics and analytics.pe_ratio is not None:
        bits = [
            f"P/E {analytics.pe_ratio:.1f}" if lang == "bn" else f"P/E is {analytics.pe_ratio:.1f}"
        ]
        if analytics.pe_vs_sector is not None:
            bits.append(
                f"সেক্টর মিডিয়ানের {analytics.pe_vs_sector:.2f} গুণ"
                if lang == "bn"
                else f"{analytics.pe_vs_sector:.2f}x sector median"
            )
        facts.append(", ".join(bits) + ("।" if lang == "bn" else "."))
    if posts_24h:
        if lang == "bn":
            extra = f", স্বাভাবিকের প্রায় {chatter_x:g} গুণ" if chatter_x else ""
            facts.append(f"প্ল্যাটফর্ম আলোচনা: গত ২৪ ঘণ্টায় {posts_24h}টি পোস্ট{extra}।")
        else:
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
    lang: Lang = "en",
    market: str = "DSE",
) -> list[ResearchInsight]:
    insights: list[ResearchInsight] = []
    profile = get_market_profile(market)
    if analytics is None:
        return [
            ResearchInsight(
                lens="valuation",
                stance="unknown",
                title="ফিন্যান্সিয়াল স্ন্যাপশট নেই" if lang == "bn" else "Financial snapshot unavailable",
                detail=(
                    "গভীর পাঠের জন্য সর্বশেষ অ্যানালিটিক্স দরকার; এই শেয়ারের ব্যবহারযোগ্য স্ন্যাপশট এখনো নেই।"
                    if lang == "bn"
                    else "The deeper read needs the latest analytics row; this symbol has no usable snapshot yet."
                ),
                evidence="টিকার অ্যানালিটিক্স নেই" if lang == "bn" else "Ticker analytics missing",
            )
        ]

    if analytics.pe_vs_sector is not None or analytics.pe_ratio is not None:
        if analytics.pe_vs_sector is not None and analytics.pe_vs_sector <= 0.8:
            stance = "constructive"
            title = (
                "সেক্টরের তুলনায় দাম কম দেখাচ্ছে"
                if lang == "bn"
                else "Valuation looks cheaper than sector"
            )
            detail = (
                "বাজার কোম্পানির আয়কে সেক্টর মিডিয়ানের নিচে মূল্য দিচ্ছে; এখন দেখতে হবে আয়ের মান ও গভর্ন্যান্স এই ডিসকাউন্ট ব্যাখ্যা করে কি না।"
                if lang == "bn"
                else "The market is pricing earnings below the sector median, so the next question is whether earnings quality and governance justify the discount."
            )
        elif analytics.pe_vs_sector is not None and analytics.pe_vs_sector >= 1.25:
            stance = "risk"
            title = (
                "দামের জন্য শক্ত প্রমাণ দরকার" if lang == "bn" else "Valuation asks for stronger proof"
            )
            detail = (
                "শেয়ারটি সেক্টর মিডিয়ানের চেয়ে প্রিমিয়ামে ট্রেড করছে, তাই দুর্বল আয় বা পুরোনো কারণ বেশি গুরুত্বপূর্ণ।"
                if lang == "bn"
                else "The stock trades at a premium to the sector median, so weak earnings or stale catalysts matter more."
            )
        else:
            stance = "watch"
            title = "দাম-মূল্য প্রধান সিগন্যাল নয়" if lang == "bn" else "Valuation is not the main signal"
            detail = (
                "ভ্যালুয়েশন সেক্টরের কাছাকাছি; দাম, ভলিউম ও ঘোষণাই এখানে বেশি ব্যাখ্যা দিতে পারে।"
                if lang == "bn"
                else "The valuation read is near the sector zone; price action and disclosures may explain more than multiples."
            )
        insights.append(
            ResearchInsight(
                lens="valuation",
                stance=stance,
                title=title,
                detail=detail,
                evidence=(
                    f"P/E {_fmt_x(analytics.pe_ratio)} · সেক্টর তুলনা {_fmt_x(analytics.pe_vs_sector)}"
                    if lang == "bn"
                    else f"P/E {_fmt_x(analytics.pe_ratio)} · sector relative {_fmt_x(analytics.pe_vs_sector)}"
                ),
            )
        )

    if analytics.rsi_14 is not None or analytics.relative_volume is not None:
        hot = analytics.rsi_14 is not None and analytics.rsi_14 >= 70
        cold = analytics.rsi_14 is not None and analytics.rsi_14 <= 30
        high_volume = analytics.relative_volume is not None and analytics.relative_volume >= 1.5
        if hot and high_volume:
            stance = "risk"
            title = "স্বল্পমেয়াদি মুভ ভিড়যুক্ত" if lang == "bn" else "Short-term move is crowded"
            detail = (
                "উচ্চ RSI ও বেশি ভলিউম মানে আগ্রহের বড় অংশ দামে চলে আসতে পারে; নতুন অফিসিয়াল খবর না থাকলে পেছনে দৌড়ানোর ঝুঁকি বেশি।"
                if lang == "bn"
                else "High RSI plus elevated volume often means attention is already in the price; chasing risk is higher unless fresh official news confirms the move."
            )
        elif cold:
            stance = "watch"
            title = (
                "ওভারসোল্ড হলে নিশ্চিতকরণ দরকার" if lang == "bn" else "Oversold zone needs confirmation"
            )
            detail = (
                "RSI কম, কিন্তু শুধু ওভারসোল্ড হওয়া কারণ নয়। স্থিতিশীলতা, ভলিউম বা অফিসিয়াল ঘটনা দেখুন।"
                if lang == "bn"
                else "RSI is low, but oversold alone is not a catalyst. Look for stabilization, volume, or an official event."
            )
        elif high_volume:
            stance = "watch"
            title = "ভলিউমই লাইভ সিগন্যাল" if lang == "bn" else "Volume is the live signal"
            detail = (
                "টার্নওভার স্বাভাবিকের চেয়ে বেশি, তাই অফিসিয়াল কারণ স্পষ্ট না হলেও মুভটি দেখা দরকার।"
                if lang == "bn"
                else "Turnover is meaningfully above normal, so the move deserves review even if the official catalyst is not obvious."
            )
        else:
            stance = "constructive"
            title = "চার্টের চাপ মাঝারি" if lang == "bn" else "Technical pressure is moderate"
            detail = (
                "স্বল্পমেয়াদি সেটআপে চরম RSI বা অস্বাভাবিক ভলিউম সতর্কতা দেখা যাচ্ছে না।"
                if lang == "bn"
                else "The short-term setup is not showing an extreme RSI or abnormal volume warning."
            )
        insights.append(
            ResearchInsight(
                lens="technical",
                stance=stance,
                title=title,
                detail=detail,
                evidence=(
                    f"RSI {_fmt_pct(analytics.rsi_14)} · ভলিউম ২০ দিনের গড়ের {analytics.relative_volume or 0:.1f} গুণ"
                    if lang == "bn"
                    else f"RSI {_fmt_pct(analytics.rsi_14)} · volume {analytics.relative_volume or 0:.1f}x 20-day average"
                ),
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
        flow_title = (
            "ফ্লো সিগন্যাল একদিকে যাচ্ছে"
            if positive and lang == "bn"
            else "বিক্রির চাপ দেখা যাচ্ছে"
            if negative and lang == "bn"
            else "ফ্লো সিগন্যাল মিশ্র"
            if lang == "bn"
            else "Accumulation signals align"
            if positive
            else "Distribution pressure is visible"
            if negative
            else "Flow signals are mixed"
        )
        insights.append(
            ResearchInsight(
                lens="liquidity",
                stance="constructive" if positive else "risk" if negative else "watch",
                title=flow_title,
                detail=(
                    "ভলিউম-ফ্লো ইন্ডিকেটর শুধু দাম ওঠা-নামা আর কেনা/বেচার চাপ আলাদা করতে সাহায্য করে; এগুলো এখনো বর্ণনামূলক সিগন্যাল।"
                    if lang == "bn"
                    else "Volume-flow indicators help separate simple price movement from buying or selling pressure, but they are still descriptive signals."
                ),
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
        ownership_title = (
            "প্রাতিষ্ঠানিক মালিকানা বেড়েছে"
            if delta > 0 and lang == "bn"
            else "প্রাতিষ্ঠানিক মালিকানা কমেছে"
            if delta < 0 and lang == "bn"
            else "মালিকানা স্থিতিশীল"
            if lang == "bn"
            else "Institutional ownership improved"
            if delta > 0
            else "Institutional ownership softened"
            if delta < 0
            else "Ownership is stable"
        )

    institutional = next((s for s in sources if s.type == "sec_13f"), None)
    if institutional:
        insights.append(
            ResearchInsight(
                lens="ownership",
                stance="watch",
                title=(
                    "প্রকাশিত প্রাতিষ্ঠানিক হোল্ডিং বদলেছে"
                    if lang == "bn"
                    else "Reported institutional holdings changed"
                ),
                detail=(
                    "১৩এফ ত্রৈমাসিক শেষের হোল্ডিং দেখায় এবং পরে প্রকাশিত হয়; এটি প্রকৃত কেনা বা বেচার তারিখ দেখায় না।"
                    if lang == "bn"
                    else "13F shows quarter-end holdings disclosed later; it does not reveal the actual purchase or sale date."
                ),
                evidence=institutional.snippet,
            )
        )
        insights.append(
            ResearchInsight(
                lens="ownership",
                stance="constructive" if delta > 0 else "risk" if delta < 0 else "watch",
                title=ownership_title,
                detail=(
                    "মালিকানার পরিবর্তন ধীর সিগন্যাল; এটি দামের মুভকে সমর্থন বা প্রশ্ন করতে পারে, কিন্তু অফিসিয়াল ঘোষণাকে ছাপিয়ে যাওয়া উচিত নয়।"
                    if lang == "bn"
                    else "Ownership change is a slow signal; it can confirm or challenge a price move but should not override disclosures."
                ),
                evidence=" · ".join(ownership_bits),
            )
        )

    official = [s for s in sources if s.reliability == "official"]
    if official:
        latest = official[0]
        exchange = profile.exchange_label(lang)
        insights.append(
            ResearchInsight(
                lens="disclosure",
                stance="watch",
                title="অফিসিয়াল ফাইলিং আছে" if lang == "bn" else "Official filing anchors the read",
                detail=(
                    f"ব্যাখ্যা শুরু করা উচিত সর্বশেষ গুরুত্বপূর্ণ {exchange} ফাইলিং থেকে, তারপর তার আশেপাশের দাম ও ভলিউম দেখা উচিত।"
                    if lang == "bn"
                    else f"The read should start from the newest material {profile.exchange_code} filing, then compare price and volume behavior around it."
                ),
                evidence=f"{latest.title} ({latest.date or ('তারিখ নেই' if lang == 'bn' else 'date unavailable')})",
            )
        )
    else:
        insights.append(
            ResearchInsight(
                lens="disclosure",
                stance="risk",
                title="এই উত্তরে অফিসিয়াল সূত্র নেই"
                if lang == "bn"
                else "No official source in this answer",
                detail=(
                    "সাম্প্রতিক অফিসিয়াল আইটেম না থাকলে মুভটি বাজারের মেকানিক্স, টেকনিক্যাল বা আলোচনাচালিত হওয়ার সম্ভাবনা বেশি।"
                    if lang == "bn"
                    else "Without a recent official item, the move is more likely driven by market mechanics, technicals, or discussion."
                ),
                evidence="র‍্যাঙ্ক করা অফিসিয়াল ঘোষণা নেই"
                if lang == "bn"
                else "No ranked official announcement",
            )
        )

    if posts_24h or chatter_x:
        insights.append(
            ResearchInsight(
                lens="crowd",
                stance="watch",
                title="আলোচনার আগ্রহ মাপা যাচ্ছে" if lang == "bn" else "Crowd attention is measurable",
                detail=(
                    "আলোচনা আগ্রহ ব্যাখ্যা করতে পারে, কিন্তু ফাইলিং বা বাজার ডেটার চেয়ে দুর্বল সূত্র।"
                    if lang == "bn"
                    else "Discussion can explain attention, but it is weaker evidence than filings or market data."
                ),
                evidence=(
                    f"২৪ ঘণ্টায় {posts_24h}টি পোস্ট"
                    + (f" · স্বাভাবিকের {chatter_x:g} গুণ" if chatter_x else "")
                    if lang == "bn"
                    else f"{posts_24h} posts in 24h"
                    + (f" · {chatter_x:g}x baseline" if chatter_x else "")
                ),
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
    lang: Lang = "en",
    market: str = "DSE",
) -> str:
    profile = get_market_profile(market)
    exchange = profile.exchange_label(lang)
    lead = ""
    if blocked_advice:
        if lang == "bn":
            lead = "আমি কেনা, বেচা, ধরে রাখা বা টার্গেট বলতে পারি না। এখনকার সূত্রগুলো সংক্ষেপে বলছি। "
        else:
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
            if lang == "bn":
                body = (
                    f"সারকথা: এই মুভের জন্য সাম্প্রতিক অফিসিয়াল সূত্র আছে। {fact_line} "
                    f"সবচেয়ে প্রাসঙ্গিক অফিসিয়াল আইটেম: {catalyst.title} "
                    f"({catalyst.date or 'তারিখ নেই'})।"
                )
            else:
                body = (
                    f"Bottom line: the move has a recent official source to review. {fact_line} "
                    f"Most relevant official item: {catalyst.title} "
                    f"({catalyst.date or 'date unavailable'})."
                )
        else:
            context = ""
            if official:
                if lang == "bn":
                    context = (
                        f" পুরোনো অফিসিয়াল প্রসঙ্গ আছে: {official[0].title} "
                        f"({official[0].date or 'তারিখ নেই'}), কিন্তু এটিকে আজকের কারণ ধরা যথেষ্ট সাম্প্রতিক নয়।"
                    )
                else:
                    context = (
                        f" Older official context exists, led by {official[0].title} "
                        f"({official[0].date or 'date unavailable'}), but it is not recent enough "
                        "to treat as today's catalyst."
                    )
            if lang == "bn":
                body = (
                    f"সারকথা: এই মুভের জন্য সাম্প্রতিক অফিসিয়াল {exchange} কারণ দেখছি না। "
                    f"{fact_line} নতুন অফিসিয়াল খবর না আসা পর্যন্ত এটিকে দাম/ভলিউম বা আলোচনাচালিত ধরে পড়ুন।{context}"
                )
            else:
                body = (
                    f"Bottom line: I do not see a recent official {profile.exchange_code} catalyst for this move. "
                    f"{fact_line} Treat this as price/volume or discussion-led until fresh official "
                    f"news appears.{context}"
                )
    elif intent in ("dividend", "earnings", "latest_news"):
        if official:
            if lang == "bn":
                body = (
                    f"সারকথা: অফিসিয়াল রেকর্ডে প্রাসঙ্গিক আইটেম আছে। {fact_line} "
                    f"সর্বশেষ প্রাসঙ্গিক অফিসিয়াল আইটেম: {official[0].title}।"
                )
            else:
                body = (
                    f"Bottom line: the official record has a relevant item. {fact_line} "
                    f"Latest relevant official item: {official[0].title}."
                )
        else:
            if lang == "bn":
                body = f"সারকথা: মিল থাকা সাম্প্রতিক অফিসিয়াল ঘোষণা পাইনি। {fact_line}"
            else:
                body = f"Bottom line: I did not find a matching recent official announcement. {fact_line}"
    elif intent == "institutional":
        holdings = [s for s in sources if s.type == "sec_13f"]
        if holdings:
            if lang == "bn":
                body = (
                    f"সারকথা: অফিসিয়াল ১৩এফ তুলনায় প্রকাশিত হোল্ডিং পরিবর্তন আছে। {fact_line} "
                    f"সর্বশেষ প্রমাণ: {holdings[0].snippet} প্রকৃত ট্রেডের তারিখ বা দাম ১৩এফে থাকে না।"
                )
            else:
                body = (
                    f"Bottom line: the official 13F comparison shows a reported holdings change. "
                    f"{fact_line} Latest evidence: {holdings[0].snippet} "
                    "13F does not disclose the manager's actual trade date or price."
                )
        else:
            body = (
                f"সারকথা: ${code}-এর জন্য নির্ভরযোগ্যভাবে মেলানো ১৩এফ ইতিহাস এখনো নেই। {fact_line}"
                if lang == "bn"
                else f"Bottom line: no confidently mapped 13F history is available for ${code} yet. {fact_line}"
            )
    elif intent == "crowd":
        if crowd:
            if lang == "bn":
                body = f"সারকথা: সাম্প্রতিক আলোচনার প্রসঙ্গ আছে। {fact_line} উদাহরণ: {crowd[0].snippet}"
            else:
                body = f"Bottom line: recent crowd context exists. {fact_line} Example: {crowd[0].snippet}"
        else:
            if lang == "bn":
                body = f"সারকথা: ${code} নিয়ে সাম্প্রতিক প্রকাশিত প্ল্যাটফর্ম আলোচনা পাইনি। {fact_line}"
            else:
                body = f"Bottom line: I did not find recent published platform discussion for ${code}. {fact_line}"
    elif intent == "red_flags":
        if official or system:
            top = (official + system)[0]
            if lang == "bn":
                body = (
                    f"সারকথা: মত তৈরি করার আগে উদ্ধৃত সূত্রগুলো দেখুন। {fact_line} প্রধান আইটেম: {top.title}।"
                )
            else:
                body = f"Bottom line: review the cited evidence before forming a view. {fact_line} Main item: {top.title}."
        else:
            if lang == "bn":
                body = f"সারকথা: সাম্প্রতিক অফিসিয়াল বা সিস্টেম রেড-ফ্ল্যাগ সূত্র পাইনি। {fact_line}"
            else:
                body = f"Bottom line: I did not find a recent official or system red-flag source. {fact_line}"
    else:
        if sources:
            if lang == "bn":
                body = f"সারকথা: সেরা উপলভ্য তথ্য সূত্রভিত্তিক। {fact_line} সবচেয়ে প্রাসঙ্গিক সূত্র: {sources[0].title}।"
            else:
                body = f"Bottom line: the best available evidence is source-backed. {fact_line} Most relevant source: {sources[0].title}."
        else:
            if lang == "bn":
                body = f"সারকথা: পূর্ণ সংক্ষিপ্ত বিশ্লেষণের জন্য যথেষ্ট সূত্র পাইনি। {fact_line}"
            else:
                body = f"Bottom line: I do not have enough retrieved evidence for a fuller brief. {fact_line}"

    suffix = (
        f" সূত্রের মান: {_quality_label(evidence_quality, lang)}। এটি তথ্যভিত্তিক পাঠ, কেনা/বেচার পরামর্শ নয়।"
        if lang == "bn"
        else f" Evidence quality: {_quality_label(evidence_quality, lang)}. This is evidence, not a trade call."
    )
    return (lead + body + suffix).strip()


async def _announcement_sources(
    session, market: str, code: str, intent: str
) -> list[ResearchSource]:
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


async def _sec_filing_sources(session, market: str, code: str, intent: str) -> list[ResearchSource]:
    categories: tuple[str, ...] | None = None
    if intent == "earnings":
        categories = ("earnings", "quarterly_report", "annual_report")
    elif intent == "red_flags":
        categories = ("current_report", "registration", "beneficial_ownership", "annual_report")
    stmt = select(SecFiling).where(SecFiling.market == market, SecFiling.code == code)
    if categories:
        stmt = stmt.where(SecFiling.category.in_(categories))
    rows = list(
        await session.scalars(
            stmt.order_by(SecFiling.filing_date.desc(), SecFiling.accepted_at.desc()).limit(8)
        )
    )
    return [
        ResearchSource(
            type="sec_filing",
            id=row.accession_number,
            title=f"SEC {row.form}: {row.category.replace('_', ' ').title()}",
            date=str(row.filing_date),
            snippet=_snippet(row.description or row.items or f"Filed for period {row.report_date}"),
            reliability="official",
            url=row.filing_url,
        )
        for row in rows
    ]


async def _sec_fact_sources(session, market: str, code: str) -> list[ResearchSource]:
    rows = list(
        await session.scalars(
            select(SecFinancialFact)
            .where(SecFinancialFact.market == market, SecFinancialFact.code == code)
            .order_by(SecFinancialFact.period_end.desc(), SecFinancialFact.filed_at.desc())
            .limit(120)
        )
    )
    by_period: dict[tuple[dt.date, str], list[SecFinancialFact]] = {}
    for row in rows:
        by_period.setdefault((row.period_end, row.period_type), []).append(row)
    sources: list[ResearchSource] = []
    for (period_end, period_type), facts in sorted(by_period.items(), reverse=True)[:4]:
        values = ", ".join(
            f"{fact.metric.replace('_', ' ')} {fact.value:,.2f} {fact.unit}" for fact in facts[:8]
        )
        source = facts[0]
        sources.append(
            ResearchSource(
                type="sec_financials",
                id=f"{code}:{period_end}:{period_type}",
                title=f"SEC financial facts: {period_type} ending {period_end}",
                date=str(source.filed_at),
                snippet=_snippet(values),
                reliability="official",
                url=source.source_url,
            )
        )
    return sources


async def _institutional_sources(session, market: str, code: str) -> list[ResearchSource]:
    rows = list(
        await session.scalars(
            select(InstitutionalHoldingSummary)
            .where(
                InstitutionalHoldingSummary.market == market,
                InstitutionalHoldingSummary.code == code,
            )
            .order_by(InstitutionalHoldingSummary.report_date.desc())
            .limit(4)
        )
    )
    return [
        ResearchSource(
            type="sec_13f",
            id=f"{code}:{row.report_date}",
            title=f"SEC 13F holdings as of {row.report_date}",
            date=str(row.latest_filing_date),
            snippet=(
                f"{row.managers_count} reporting managers held {row.total_shares:,} shares; "
                f"quarter-over-quarter comparable-share change {row.net_change_pct:+.2f}%. "
                f"New {row.new_positions}, increased {row.increased_positions}, "
                f"reduced {row.reduced_positions}, exited {row.exited_positions}."
                if row.net_change_pct is not None
                else f"{row.managers_count} reporting managers held {row.total_shares:,} shares."
            ),
            reliability="official",
            url=row.source_url,
        )
        for row in rows
    ]


async def _post_sources(session, market: str, code: str, *, tenant_id: str) -> list[ResearchSource]:
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=7)
    tagged = select(Cashtag.post_id).where(Cashtag.market == market, Cashtag.code == code)
    rows = list(
        await session.scalars(
            select(Post)
            .where(
                Post.id.in_(tagged),
                Post.tenant_id == tenant_id,
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


async def _signal_sources(
    session, market: str, code: str, *, tenant_id: str
) -> list[ResearchSource]:
    rows = list(
        await session.scalars(
            select(SignalEvent)
            .where(
                SignalEvent.tenant_id == tenant_id,
                SignalEvent.market == market,
                SignalEvent.code == code,
            )
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


async def _vector_sources(
    session, market: str, code: str, question: str, *, tenant_id: str
) -> list[ResearchSource]:
    try:
        chunks = await retrieve(
            session, question, market=market, tenant_id=tenant_id, code=code, k=8
        )
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
            url=(c.metadata or {}).get("url"),
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
    lang: Lang = _LANG_QUERY,
) -> ResearchBriefResponse:
    enforce_market_feature(tenant, "interpreted_analytics")
    code = code.upper()
    symbol = await session.get(Symbol, (tenant.market, code))
    if symbol is None or not symbol.is_retail_ready:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")

    intent = _intent(q)
    quote = (
        await load_freshest_quotes(
            session,
            tenant.market,
            [code],
            get_market_profile(tenant.market).tz,
        )
    ).get(code)
    analytics = await session.get(TickerAnalytics, (tenant.market, code))
    buzz = await gather_buzz(session, tenant.market, code, tenant_id=tenant.name)

    facts = _facts(
        code=code,
        quote=quote,
        analytics=analytics,
        posts_24h=buzz.posts_24h,
        chatter_x=buzz.chatter_x,
        lang=lang,
        market=tenant.market,
    )
    vector_sources = await _vector_sources(session, tenant.market, code, q, tenant_id=tenant.name)
    announcement_sources = await _announcement_sources(session, tenant.market, code, intent)
    sec_filing_sources: list[ResearchSource] = []
    sec_fact_sources: list[ResearchSource] = []
    institutional_sources: list[ResearchSource] = []
    if get_market_profile(tenant.market).features.sec_filings:
        sec_filing_sources = await _sec_filing_sources(session, tenant.market, code, intent)
        sec_fact_sources = await _sec_fact_sources(session, tenant.market, code)
    if get_market_profile(tenant.market).features.institutional_holdings:
        institutional_sources = await _institutional_sources(session, tenant.market, code)
    signal_sources = await _signal_sources(session, tenant.market, code, tenant_id=tenant.name)
    post_sources = await _post_sources(session, tenant.market, code, tenant_id=tenant.name)
    sources = [
        *vector_sources,
        *announcement_sources,
        *sec_filing_sources,
        *sec_fact_sources,
        *institutional_sources,
        *signal_sources,
        *post_sources,
    ]
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
        lang=lang,
        market=tenant.market,
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
        lang=lang,
        market=tenant.market,
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
