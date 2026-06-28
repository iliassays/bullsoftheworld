"""Compose ready-to-publish Facebook posts from the app's own data.

One composer per pillar; each returns a ComposedPost (bilingual caption + branded card PNG + link).
Deterministic — no LLM — so it's free, reliable, and stays on the descriptive/no-advice line.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select

from api.deps import visible_codes
from api.fb import cards
from bulls.core.models import MarketSummary, QuoteSnapshot

LINK = "https://bullsofdhaka.com"
_NO_ADVICE_BN = "তথ্যমূলক, পরামর্শ নয়।"
_NO_ADVICE_EN = "Descriptive data, not advice."


@dataclass
class ComposedPost:
    kind: str
    ref_date: str
    caption: str
    png: bytes
    link: str


def _movers_str(movers: list[cards.Mover]) -> str:
    return ", ".join(f"${m.code} {m.change_pct:+.1f}%" for m in movers[:3]) or "—"


def index_pct(dsex: float | None, points: float | None) -> float | None:
    """MarketSummary.dsex_change is the day's POINT change, not a percent. Convert to %, and
    omit (None) anything implausible for an index in a day — better blank than misleading."""
    if dsex is None or points is None:
        return None
    prev = dsex - points
    if not prev:
        return None
    pct = points / prev * 100
    return pct if abs(pct) <= 20 else None


def evening_caption(d: cards.EveningWrapData) -> str:
    """Pure caption builder (bilingual). Numbers stay Western numerals."""
    dsex = "—" if d.dsex is None else f"{d.dsex:,.0f}"
    chg = "" if d.dsex_change is None else f" ({d.dsex_change:+.2f}%)"
    turnover = "" if d.turnover_cr is None else f" · টার্নওভার Tk {d.turnover_cr:,.0f} কোটি"
    turnover_en = "" if d.turnover_cr is None else f" · turnover Tk {d.turnover_cr:,.0f} cr"
    movers = _movers_str(d.movers)
    bn = (
        f"🌙 ইভিনিং র‍্যাপ — {d.date_label}\n"
        f"DSEX {dsex}{chg} · {d.advancers}টি বেড়েছে, {d.decliners}টি কমেছে{turnover}।\n"
        f"শীর্ষ মুভার: {movers}।\n{_NO_ADVICE_BN}"
    )
    en = (
        f"🌙 Evening Wrap — {d.date_label}\n"
        f"DSEX {dsex}{chg} · {d.advancers} up, {d.decliners} down{turnover_en}.\n"
        f"Top movers: {movers}.\n{_NO_ADVICE_EN}"
    )
    return f"{bn}\n\n{en}\n\n👉 {LINK}"


async def compose_evening_wrap(session, market: str) -> ComposedPost:
    summary = await session.scalar(
        select(MarketSummary)
        .where(MarketSummary.market == market)
        .order_by(MarketSummary.date.desc())
        .limit(1)
    )
    if summary is None:
        raise cards.CardError("no market summary available")

    vis = visible_codes(market)
    adv = await session.scalar(
        select(func.count()).where(
            QuoteSnapshot.market == market,
            QuoteSnapshot.code.in_(vis),
            QuoteSnapshot.change_pct > 0,
        )
    )
    dec = await session.scalar(
        select(func.count()).where(
            QuoteSnapshot.market == market,
            QuoteSnapshot.code.in_(vis),
            QuoteSnapshot.change_pct < 0,
        )
    )
    flat = await session.scalar(
        select(func.count()).where(
            QuoteSnapshot.market == market,
            QuoteSnapshot.code.in_(vis),
            QuoteSnapshot.change_pct == 0,
        )
    )
    rows = (
        await session.execute(
            select(QuoteSnapshot.code, QuoteSnapshot.change_pct)
            .where(
                QuoteSnapshot.market == market,
                QuoteSnapshot.code.in_(vis),
                QuoteSnapshot.ltp > 0,
            )
            .order_by(QuoteSnapshot.change_pct.desc())
            .limit(6)
        )
    ).all()
    movers = [cards.Mover(code=c, change_pct=p or 0.0) for c, p in rows]

    data = cards.EveningWrapData(
        date_label=summary.date.strftime("%d %b %Y"),
        dsex=summary.dsex,
        dsex_change=index_pct(summary.dsex, summary.dsex_change),
        advancers=adv or 0,
        decliners=dec or 0,
        unchanged=flat or 0,
        turnover_cr=(summary.total_value_mn / 10) if summary.total_value_mn else None,
        movers=movers,
    )
    return ComposedPost(
        kind="evening_wrap",
        ref_date=str(summary.date),
        caption=evening_caption(data),
        png=cards.evening_wrap_card(data),
        link=LINK,
    )
