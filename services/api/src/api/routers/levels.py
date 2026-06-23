"""Key levels & what to watch — deterministic, templated, localized. No LLM, no advice.

The analytics engine gives the facts; we render them into educational "what to watch" sentences
from fixed templates. Templated (not generated) on purpose: this is prediction-sensitive content,
and a template can never drift into a forecast or a recommendation.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from api.deps import CurrentTenant, DbSession
from bulls.analytics import LevelsInsight, build_levels, compute
from bulls.core.models import DailyBar, Symbol

router = APIRouter(tags=["levels"])

_LOOKBACK = 260


class LevelsResponse(BaseModel):
    code: str
    as_of: str
    insight: LevelsInsight
    lines: list[str]


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
    lines.append("দেখার মতো লেভেল ও ধারণা — কোনো ভবিষ্যদ্বাণী বা পরামর্শ নয়।")
    return lines


@router.get("/symbols/{code}/levels")
async def get_levels(code: str, tenant: CurrentTenant, session: DbSession) -> LevelsResponse:
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

    render = _render_bn if tenant.locale == "bn" else _render_en
    return LevelsResponse(
        code=code, as_of=str(result.as_of_date), insight=insight, lines=render(code, insight)
    )
