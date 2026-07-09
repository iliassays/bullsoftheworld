"""Key levels & what to watch — deterministic, templated, localized. No LLM, no advice.

The analytics engine gives the facts; we render them into educational "what to watch" sentences
from fixed templates. Templated (not generated) on purpose: this is prediction-sensitive content,
and a template can never drift into a forecast or a recommendation.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from api.deps import CurrentLocale, CurrentTenant, DbSession
from bulls.analytics import LevelsInsight, build_levels, compute
from bulls.core.models import DailyBar, QuoteSnapshot, Symbol
from bulls.market_data.calendar import Session, session_phase

router = APIRouter(tags=["levels"])

_LOOKBACK = 260
_NEAR = 0.01  # within 1% counts as "testing" a level


class LevelsResponse(BaseModel):
    code: str
    as_of: str
    insight: LevelsInsight
    lines: list[str]
    # The live (delayed) price's position vs the as-of-close levels — only while the market is open.
    live_line: str | None = None


def _relation(price: float, support: float | None, resistance: float | None) -> str:
    if support is not None and price < support:
        return "below_support"
    if resistance is not None and price > resistance:
        return "above_resistance"
    if support is not None and price <= support * (1 + _NEAR):
        return "near_support"
    if resistance is not None and price >= resistance * (1 - _NEAR):
        return "near_resistance"
    if support is not None and resistance is not None and support < price < resistance:
        return "between"
    return "unknown"


def _live_en(price: float, rel: str, s: float | None, r: float | None) -> str:
    # Build only the selected branch: _relation guarantees s (resp. r) is set for the support
    # (resp. resistance) cases, but a dict literal would eagerly format every branch and crash on
    # a one-sided level where the other side is None.
    p = f"Live (delayed) ৳{price:g}"
    if rel == "below_support":
        return f"{p} — now below the ৳{s:g} support from last close; a daily close below confirms a break."
    if rel == "near_support":
        return f"{p} — now testing the ৳{s:g} support from last close."
    if rel == "above_resistance":
        return f"{p} — now above the ৳{r:g} resistance from last close; a daily close above confirms a breakout."
    if rel == "near_resistance":
        return f"{p} — now testing the ৳{r:g} resistance from last close."
    if rel == "between":
        return f"{p} — trading between support ৳{s:g} and resistance ৳{r:g} (from last close)."
    return f"{p}."


def _live_bn(price: float, rel: str, s: float | None, r: float | None) -> str:
    # Build only the selected branch — see _live_en: a dict literal crashes on one-sided levels.
    p = f"লাইভ (বিলম্বিত) ৳{price:g}"
    if rel == "below_support":
        return f"{p} — এখন গত ক্লোজের ৳{s:g} সাপোর্টের নিচে; দিন শেষে নিচে ক্লোজ হলে ব্রেক নিশ্চিত।"
    if rel == "near_support":
        return f"{p} — এখন গত ক্লোজের ৳{s:g} সাপোর্ট পরীক্ষা করছে।"
    if rel == "above_resistance":
        return (
            f"{p} — এখন গত ক্লোজের ৳{r:g} রেজিস্ট্যান্সের উপরে; দিন শেষে উপরে ক্লোজ হলে ব্রেকআউট নিশ্চিত।"
        )
    if rel == "near_resistance":
        return f"{p} — এখন গত ক্লোজের ৳{r:g} রেজিস্ট্যান্স পরীক্ষা করছে।"
    if rel == "between":
        return f"{p} — গত ক্লোজের সাপোর্ট ৳{s:g} ও রেজিস্ট্যান্স ৳{r:g} এর মধ্যে লেনদেন হচ্ছে।"
    return f"{p}।"


def _f(n: float | None) -> str:
    return "—" if n is None else f"{n:g}"


def _render_en(code: str, i: LevelsInsight) -> list[str]:
    lines: list[str] = []
    if i.pa_change_pct is not None:
        verb = {"rising": "risen", "falling": "fallen", "flat": "been roughly flat"}[i.pa_direction]
        lines.append(
            f"{code} has {verb} over the last {i.pa_sessions} sessions ({i.pa_change_pct:+.1f}%)."
        )
    if i.resistance is not None:
        vol = "above" if i.volume_confirms else "below"
        lines.append(
            f"Resistance ৳{_f(i.resistance)} — a daily close above this is a breakout, confirmed "
            f"on above-average volume; on weak volume technicians treat it as unconfirmed and prone "
            f"to failing. (Volume is {vol} its 20-day average now.)"
        )
    if i.support is not None:
        lines.append(
            f"Support ৳{_f(i.support)} — a close below this breaks support, and the next lower "
            f"level comes into focus. A dip below that closes back above is a support reclaim."
        )
    if i.rsi is not None and i.rsi_zone:
        note = {
            "overbought": "historically, moves can stall here",
            "oversold": "historically, selling can exhaust here",
            "neutral": "in a neutral range",
        }[i.rsi_zone]
        lines.append(
            f"RSI {i.rsi:.0f} ({i.rsi_zone} zone) — {note}. A concept to watch, not a forecast."
        )
    # When no confirmed pivot sits on the right side of the close, we have no trustworthy
    # support/resistance — say so plainly rather than invent a level. Honest absence beats a
    # fabricated number for prices people invest on.
    if i.resistance is None and i.support is None:
        lines.append(
            "Not enough confirmed price history to identify support or resistance levels yet."
        )
        lines.append("Not predictions or advice.")
    else:
        lines.append("Levels and concepts to watch — not predictions or advice.")
    return lines


def _render_bn(code: str, i: LevelsInsight) -> list[str]:
    lines: list[str] = []
    if i.pa_change_pct is not None:
        verb = {
            "rising": "বেড়েছে",
            "falling": "কমেছে",
            "flat": "প্রায় অপরিবর্তিত ছিল",
        }[i.pa_direction]
        lines.append(f"{code} গত {i.pa_sessions} সেশনে {verb} ({i.pa_change_pct:+.1f}%)।")
    if i.resistance is not None:
        vol = "উপরে" if i.volume_confirms else "নিচে"
        lines.append(
            f"রেজিস্ট্যান্স ৳{_f(i.resistance)} — এর উপরে দিন শেষে ক্লোজ হলে তাকে ব্রেকআউট বলে; "
            f"গড়ের বেশি ভলিউমে হলে তা নিশ্চিত ধরা হয়, কম ভলিউমে অনিশ্চিত ও ব্যর্থ হতে পারে। "
            f"(এখন ভলিউম তার ২০-দিনের গড়ের {vol}।)"
        )
    if i.support is not None:
        lines.append(
            f"সাপোর্ট ৳{_f(i.support)} — এর নিচে ক্লোজ হলে সাপোর্ট ভেঙে যায়, পরের নিচের লেভেল "
            f"গুরুত্বপূর্ণ হয়ে ওঠে। নিচে নেমে আবার উপরে ক্লোজ করলে তাকে সাপোর্ট রিক্লেইম বলে।"
        )
    if i.rsi is not None and i.rsi_zone:
        zone = {
            "overbought": "অতিরিক্ত কেনা",
            "oversold": "অতিরিক্ত বিক্রি",
            "neutral": "নিরপেক্ষ",
        }[i.rsi_zone]
        note = {
            "overbought": "সাধারণত এখানে মুভমেন্ট থমকে যেতে পারে",
            "oversold": "সাধারণত এখানে বিক্রির চাপ কমে আসতে পারে",
            "neutral": "এটি একটি নিরপেক্ষ অবস্থানে আছে",
        }[i.rsi_zone]
        lines.append(f"RSI {i.rsi:.0f} ({zone} জোন) — {note}। দেখার মতো ধারণা, ভবিষ্যদ্বাণী নয়।")
    # No trustworthy support/resistance → say so honestly, never fabricate a level.
    if i.resistance is None and i.support is None:
        lines.append(
            "এখনো নির্ভরযোগ্য সাপোর্ট বা রেজিস্ট্যান্স লেভেল চিহ্নিত করার মতো যথেষ্ট নিশ্চিত প্রাইস ডেটা নেই।"
        )
        lines.append("কোনো ভবিষ্যদ্বাণী বা পরামর্শ নয়।")
    else:
        lines.append("দেখার মতো লেভেল ও ধারণা — কোনো ভবিষ্যদ্বাণী বা পরামর্শ নয়।")
    return lines


@router.get("/symbols/{code}/levels")
async def get_levels(
    code: str, tenant: CurrentTenant, session: DbSession, locale: CurrentLocale
) -> LevelsResponse:
    code = code.upper()
    symbol = await session.get(Symbol, (tenant.market, code))
    if symbol is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol {code!r}")

    bars = list(
        await session.scalars(
            select(DailyBar)
            .where(DailyBar.market == tenant.market, DailyBar.code == code)
            .order_by(DailyBar.date.desc())
            .limit(_LOOKBACK)
        )
    )
    if not bars:
        raise HTTPException(status_code=404, detail=f"No price history for {code!r} yet")
    bars.reverse()
    result = compute(bars)
    insight = build_levels(result, [b.close for b in bars])

    render = _render_bn if locale == "bn" else _render_en

    # Bridge the two clocks: while the market is open, show the live (delayed) price's position
    # relative to the as-of-close levels. Outside hours the EOD card stands on its own.
    live_line: str | None = None
    if (
        session_phase(dt.datetime.now(dt.UTC), ZoneInfo(tenant.timezone), market=tenant.market)
        is Session.OPEN
    ):
        quote = await session.get(QuoteSnapshot, (tenant.market, code))
        price = quote.ltp if quote else result.last_close
        rel = _relation(price, insight.support, insight.resistance)
        live_fn = _live_bn if locale == "bn" else _live_en
        live_line = live_fn(price, rel, insight.support, insight.resistance)

    return LevelsResponse(
        code=code,
        as_of=str(result.as_of_date),
        insight=insight,
        lines=render(code, insight),
        live_line=live_line,
    )
