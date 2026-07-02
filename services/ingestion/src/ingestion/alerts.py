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

from bulls.core.models import AlertEvent, PortfolioHolding, PriceAlert, WatchlistItem

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
    "sponsor_stake_down": {
        "en": "${code} sponsor holding fell",
        "bn": "${code} স্পনসরদের শেয়ার কমেছে",
    },
    "sponsor_stake_up": {
        "en": "${code} sponsor holding rose",
        "bn": "${code} স্পনসরদের শেয়ার বেড়েছে",
    },
    "institute_stake_down": {
        "en": "${code} institutional holding fell",
        "bn": "${code} প্রাতিষ্ঠানিক শেয়ার কমেছে",
    },
    "institute_stake_up": {
        "en": "${code} institutional holding rose",
        "bn": "${code} প্রাতিষ্ঠানিক শেয়ার বেড়েছে",
    },
    "foreign_stake_down": {
        "en": "${code} foreign holding fell",
        "bn": "${code} বিদেশি শেয়ার কমেছে",
    },
    "foreign_stake_up": {
        "en": "${code} foreign holding rose",
        "bn": "${code} বিদেশি শেয়ার বেড়েছে",
    },
}
_FALLBACK_TITLE = {"en": "New data note for ${code}", "bn": "${code} নিয়ে নতুন ডেটা নোট"}

# Ownership events are alert kind "ownership"; everything else from agents is "signal".
_OWNERSHIP_PREFIXES = ("sponsor_", "institute_", "foreign_")


def note_alert_title(event_type: str, code: str) -> dict[str, str]:
    tpl = NOTE_ALERT_TITLES.get(event_type, _FALLBACK_TITLE)
    return {lang: text.replace("{code}", code) for lang, text in tpl.items()}


def note_alert_kind(event_type: str) -> str:
    return "ownership" if event_type.startswith(_OWNERSHIP_PREFIXES) else "signal"


def should_trigger(direction: str, level: float, ltp: float) -> bool:
    return ltp >= level if direction == "above" else ltp <= level


async def _interested_user_ids(session, market: str, code: str) -> list[int]:
    """Watchers plus holders — the audience for a stock's data events."""
    watchers = select(WatchlistItem.user_id).where(
        WatchlistItem.market == market, WatchlistItem.code == code
    )
    holders = select(PortfolioHolding.user_id).where(
        PortfolioHolding.market == market, PortfolioHolding.code == code
    )
    return list(await session.scalars(union(watchers, holders)))


async def fan_out_note_alert(
    session,
    *,
    market: str,
    code: str,
    event_type: str,
    body_i18n: dict[str, str] | None,
    ref_post_id: int | None,
) -> int:
    """One inbox row per interested user. Returns the fan-out count (for logs)."""
    user_ids = await _interested_user_ids(session, market, code)
    title = note_alert_title(event_type, code)
    kind = note_alert_kind(event_type)
    for uid in user_ids:
        session.add(
            AlertEvent(
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


def _price_cross_texts(code: str, direction: str, level: float, ltp: float) -> tuple[dict, dict]:
    arrow = "above" if direction == "above" else "below"
    arrow_bn = "উপরে" if direction == "above" else "নিচে"
    title = {
        "en": f"Price alert: ${code} {arrow} ৳{level:g}",
        "bn": f"দামের অ্যালার্ট: ${code} ৳{level:g} এর {arrow_bn}",
    }
    body = {
        "en": f"Your level. Now ৳{ltp:g}.",
        "bn": f"আপনার সেট করা দাম। এখন ৳{ltp:g}।",
    }
    return title, body


async def check_price_alerts(session, market: str, prices: dict[str, float]) -> int:
    """Fire untriggered price alerts against the latest poll. One-shot per alert row."""
    if not prices:
        return 0
    pending = (
        await session.scalars(
            select(PriceAlert).where(
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
        title, body = _price_cross_texts(alert.code, alert.direction, alert.level, ltp)
        session.add(
            AlertEvent(
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
