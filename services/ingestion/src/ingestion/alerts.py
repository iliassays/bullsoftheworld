"""Alert fan-out — turn data events into per-user inbox rows.

Two producers:
  * publish_note() calls fan_out_note_alert() so every agent signal reaches the users watching
    or holding that stock (write-time fan-out; the watcher count per DSE ticker is small).
  * poll_market() calls check_price_alerts() after each quote upsert; a level fires exactly once
    (triggered_at set in the same transaction that writes the inbox row).

Titles are deterministic bilingual templates keyed by event_type — never model output, so the
inbox stays drift-safe and no-advice by construction.
"""

from __future__ import annotations

from sqlalchemy import func, select, union
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bulls.core.db import bind_tenant_context
from bulls.core.markets import get_market_profile
from bulls.core.models import AlertEvent, PortfolioHolding, PriceAlert, User, WatchlistItem

# Short bilingual headlines per levels-agent event type. The full note body rides along as the
# alert body, so the inbox row reads: what happened (title) + the desk's own words (body).
NOTE_ALERT_TITLES: dict[str, dict[str, str]] = {
    "new_52w_high": {
        "en": "${code} hit a new 52-week high",
        "bn": "${code} নতুন ৫২-সপ্তাহের সর্বোচ্চে",
    },
    "new_52w_low": {
        "en": "${code} hit a new 52-week low",
        "bn": "${code} নতুন ৫২-সপ্তাহের সর্বনিম্নে",
    },
    "breakout": {
        "en": "${code} broke above resistance",
        "bn": "${code} রেজিস্ট্যান্সের উপরে উঠেছে",
    },
    "breakdown": {
        "en": "${code} fell below support",
        "bn": "${code} সাপোর্টের নিচে নেমেছে",
    },
    "ma200_cross_up": {
        "en": "${code} crossed above its 200-day average",
        "bn": "${code} ২০০-দিনের গড়ের উপরে উঠেছে",
    },
    "ma200_cross_down": {
        "en": "${code} crossed below its 200-day average",
        "bn": "${code} ২০০-দিনের গড়ের নিচে নেমেছে",
    },
    "rsi_overbought": {
        "en": "${code} entered the overbought zone (RSI)",
        "bn": "${code} ওভারবট জোনে ঢুকেছে (RSI)",
    },
    "rsi_oversold": {
        "en": "${code} entered the oversold zone (RSI)",
        "bn": "${code} ওভারসোল্ড জোনে ঢুকেছে (RSI)",
    },
    # Ownership agent event types (direction lives in the note body the alert carries along).
    "sponsor_change": {
        "en": "${code} sponsor/director holding changed",
        "bn": "${code} স্পনসর/পরিচালকদের শেয়ারে পরিবর্তন",
    },
    "institution_change": {
        "en": "${code} institutional holding changed",
        "bn": "${code} প্রাতিষ্ঠানিক শেয়ারে পরিবর্তন",
    },
    "foreign_change": {
        "en": "${code} foreign holding changed",
        "bn": "${code} বিদেশি শেয়ারে পরিবর্তন",
    },
    "sponsor_falling_streak": {
        "en": "${code} sponsor holding falling for months",
        "bn": "${code} স্পনসরদের শেয়ার মাসের পর মাস কমছে",
    },
    # Volume desk
    "unusual_volume": {
        "en": "${code} is unusually active today",
        "bn": "${code} আজ অস্বাভাবিক সক্রিয়",
    },
    # Factor desks
    "momentum_strong": {
        "en": "${code} is one of the strongest 12-month trends",
        "bn": "${code} সবচেয়ে শক্তিশালী ১২-মাসের প্রবণতার একটি",
    },
    "quality_value": {
        "en": "${code} trades cheap vs its sector with strong ROE",
        "bn": "${code} খাতের তুলনায় সস্তা, ROE শক্তিশালী",
    },
    "smart_money_both": {
        "en": "${code}: institutions and foreign investors both raised stakes",
        "bn": "${code}: প্রতিষ্ঠান ও বিদেশি উভয়েই অংশ বাড়িয়েছে",
    },
    "quiet_accumulation": {
        "en": "${code} shows quiet accumulation",
        "bn": "${code}-তে নীরব সঞ্চয়ের ছাপ",
    },
    "rel_strength": {
        "en": "${code} rose while the market fell",
        "bn": "বাজার পড়লেও ${code} বেড়েছে",
    },
    "circuit_up": {
        "en": "${code} hit its upper price limit",
        "bn": "${code} ঊর্ধ্ব দামসীমা ছুঁয়েছে",
    },
    "circuit_down": {
        "en": "${code} hit its lower price limit",
        "bn": "${code} নিম্ন দামসীমা ছুঁয়েছে",
    },
    # News desks
    "news_earnings": {"en": "${code} earnings update", "bn": "${code} আয়ের আপডেট"},
    "news_dividend": {"en": "${code} dividend update", "bn": "${code} লভ্যাংশ আপডেট"},
    "news_rating": {"en": "${code} credit rating update", "bn": "${code} ক্রেডিট রেটিং আপডেট"},
}
_FALLBACK_TITLE = {"en": "New data note for ${code}", "bn": "${code} নিয়ে নতুন ডেটা নোট"}

# Ownership events are alert kind "ownership"; earnings/dividend news get the calendar kind;
# everything else from agents is "signal". Kinds drive the inbox icon.
_OWNERSHIP_EVENTS = frozenset(
    {"sponsor_change", "institution_change", "foreign_change", "sponsor_falling_streak"}
)
_EARNINGS_EVENTS = frozenset({"news_earnings", "news_dividend"})


def note_alert_title(event_type: str, code: str) -> dict[str, str]:
    tpl = NOTE_ALERT_TITLES.get(event_type, _FALLBACK_TITLE)
    return {lang: text.replace("{code}", code) for lang, text in tpl.items()}


def note_alert_kind(event_type: str) -> str:
    if event_type in _OWNERSHIP_EVENTS:
        return "ownership"
    if event_type in _EARNINGS_EVENTS:
        return "earnings"
    return "signal"


def should_trigger(direction: str, level: float, ltp: float) -> bool:
    return ltp >= level if direction == "above" else ltp <= level


async def _interested_user_ids(session, tenant_id: str, market: str, code: str) -> list[int]:
    """Watchers plus holders — the audience for a stock's data events."""
    await bind_tenant_context(session, tenant_id)
    watchers = (
        select(WatchlistItem.user_id)
        .join(User, User.id == WatchlistItem.user_id)
        .where(
            User.tenant_id == tenant_id,
            WatchlistItem.market == market,
            WatchlistItem.code == code,
        )
    )
    holders = (
        select(PortfolioHolding.user_id)
        .join(User, User.id == PortfolioHolding.user_id)
        .where(
            User.tenant_id == tenant_id,
            PortfolioHolding.market == market,
            PortfolioHolding.code == code,
        )
    )
    return list(await session.scalars(union(watchers, holders)))


async def fan_out_note_alert(
    session,
    *,
    tenant_id: str,
    market: str,
    code: str,
    event_type: str,
    body_i18n: dict[str, str] | None,
    ref_post_id: int | None,
) -> int:
    """One inbox row per interested user. Returns the fan-out count (for logs)."""
    user_ids = await _interested_user_ids(session, tenant_id, market, code)
    title = note_alert_title(event_type, code)
    kind = note_alert_kind(event_type)
    for uid in user_ids:
        session.add(
            AlertEvent(
                tenant_id=tenant_id,
                user_id=uid,
                market=market,
                code=code,
                kind=kind,
                title_i18n=title,
                body_i18n=body_i18n,
                ref_post_id=ref_post_id,
            )
        )
    return len(user_ids)


async def fan_out_evidence_alert(
    session,
    *,
    tenant_id: str,
    market: str,
    code: str,
    source_key: str,
    kind: str,
    title_i18n: dict[str, str],
    body_i18n: dict[str, str] | None,
) -> int:
    """Deliver one idempotent alert per watcher/holder for external official evidence."""
    user_ids = await _interested_user_ids(session, tenant_id, market, code)
    if not user_ids:
        return 0
    rows = [
        {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "market": market,
            "code": code,
            "kind": kind,
            "title_i18n": title_i18n,
            "body_i18n": body_i18n,
            "source_key": source_key,
        }
        for user_id in user_ids
    ]
    stmt = pg_insert(AlertEvent).values(rows)
    result = await session.execute(
        stmt.on_conflict_do_nothing(
            index_elements=["tenant_id", "user_id", "source_key"],
            index_where=AlertEvent.source_key.isnot(None),
        )
    )
    return max(0, int(result.rowcount or 0))


def sec_filing_alert_text(
    code: str, form: str, filing_date: object, description: str | None
) -> tuple[dict[str, str], dict[str, str]]:
    detail = (description or "Official filing published").strip()
    return (
        {"en": f"${code} filed {form} with the SEC"},
        {
            "en": (
                f"Published {filing_date}. {detail[:180]} Review the official filing before "
                "interpreting any price move."
            )
        },
    )


def institutional_alert_text(
    code: str,
    report_date: object,
    net_change_pct: float | None,
    managers_count: int,
) -> tuple[dict[str, str], dict[str, str]]:
    direction = "increased" if (net_change_pct or 0) >= 0 else "reduced"
    change = (
        f"{abs(net_change_pct):.1f}%" if net_change_pct is not None else "an unavailable amount"
    )
    return (
        {"en": f"${code} institutional holdings update"},
        {
            "en": (
                f"Aggregate Form 13F reported shares {direction} {change} for the quarter ended "
                f"{report_date}, across {managers_count} reporting managers. 13F is delayed and "
                "does not reveal trade dates, prices, shorts, or intent."
            )
        },
    )


def _price_cross_texts(
    code: str,
    direction: str,
    level: float,
    ltp: float,
    set_on: object = None,
    *,
    currency: str = "৳",
) -> tuple[dict, dict]:
    arrow = "above" if direction == "above" else "below"
    arrow_bn = "উপরে" if direction == "above" else "নিচে"
    when = f" on {set_on:%d %b}" if set_on else ""
    when_bn = f" {set_on:%d %b} তারিখে" if set_on else ""
    title = {
        "en": f"Price alert: ${code} crossed {arrow} {currency}{level:g}",
        "bn": f"দামের অ্যালার্ট: ${code} {currency}{level:g} এর {arrow_bn} গেছে",
    }
    body = {
        "en": f"The level you set{when}. Now {currency}{ltp:g}.",
        "bn": f"আপনি{when_bn} এই দাম সেট করেছিলেন। এখন {currency}{ltp:g}।",
    }
    return title, body


async def check_price_alerts(session, tenant_id: str, market: str, prices: dict[str, float]) -> int:
    """Fire untriggered price alerts against the latest poll. One-shot per alert row."""
    if not prices:
        return 0
    await bind_tenant_context(session, tenant_id)
    pending = (
        await session.scalars(
            select(PriceAlert).where(
                PriceAlert.tenant_id == tenant_id,
                PriceAlert.market == market,
                PriceAlert.triggered_at.is_(None),
                PriceAlert.code.in_(prices.keys()),
            )
        )
    ).all()
    fired = 0
    for alert in pending:
        ltp = prices.get(alert.code)
        if ltp is None or not should_trigger(alert.direction, alert.level, ltp):
            continue
        alert.triggered_at = func.now()
        title, body = _price_cross_texts(
            alert.code,
            alert.direction,
            alert.level,
            ltp,
            alert.created_at,
            currency=get_market_profile(market).currency_symbol,
        )
        session.add(
            AlertEvent(
                tenant_id=alert.tenant_id,
                user_id=alert.user_id,
                market=market,
                code=alert.code,
                kind="price_cross",
                title_i18n=title,
                body_i18n=body,
            )
        )
        fired += 1
    return fired
