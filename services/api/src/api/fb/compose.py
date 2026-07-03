"""Compose ready-to-publish Facebook posts from the app's own data.

One composer per pillar; each returns a ComposedPost (bilingual caption + branded card PNG + link).
Deterministic — no LLM — so it's free, reliable, and stays on the descriptive/no-advice line.
"""

from __future__ import annotations

import base64
import datetime as dt
from dataclasses import dataclass

from sqlalchemy import and_, func, or_, select

from api.deps import visible_codes
from api.fb import cards
from bulls.core.models import (
    Announcement,
    CompanyLogo,
    DailyBar,
    MarketSummary,
    QuoteSnapshot,
    Symbol,
    TickerAnalytics,
)
from bulls.market_data.calendar import to_market_tz

LINK = "https://bullsofdhaka.com"
MARKETS_LINK = f"{LINK}/markets"
_NO_ADVICE_BN = "তথ্যমূলক ডেটা, বিনিয়োগ পরামর্শ নয়।"
_NO_ADVICE_EN = "Descriptive data only, not investment advice."


def _campaign_link(campaign: str) -> str:
    return f"{MARKETS_LINK}?utm_source=facebook&utm_medium=social&utm_campaign={campaign}"


def _market_cta(campaign: str) -> str:
    link = _campaign_link(campaign)
    if campaign == "morning_watch":
        return (
            "🔎 আজকের Market Pulse, Active Today ও ADTV/Order Guide দেখুন:\n"
            "See today's Market Pulse, Active Today and ADTV/Order Guide:\n"
            f"👉 {link}"
        )
    if campaign == "evening_wrap":
        return (
            "🔎 পুরো Evening Wrap, সেক্টর হিটম্যাপ ও স্টক ডিটেইলস দেখুন:\n"
            "See the full Evening Wrap, sector heatmap and stock pages:\n"
            f"👉 {link}"
        )
    return (
        "🔎 পুরো মার্কেট বোর্ড, সেক্টর হিটম্যাপ ও স্টক ডিটেইলস দেখুন:\n"
        "Explore full market boards, sector heatmap and stock pages:\n"
        f"👉 {link}"
    )


# Keep public Facebook radar posts on the same investable universe as the Market page.
_MIN_ADTV_MN = 5.0  # average daily turnover over 20 sessions, Tk millions
_MIN_MCAP_MN = 500.0  # market capitalisation, Tk millions
_MIN_FREE_FLOAT_CAP_MN = 100.0  # applied when available, Tk millions


def _screenable_codes(market: str):
    return select(Symbol.code).where(
        Symbol.market == market,
        Symbol.is_active.is_(True),
        Symbol.is_hidden.is_(False),
        or_(Symbol.category.is_(None), Symbol.category != "Z"),
    )


def _liquid_universe():
    return and_(
        TickerAnalytics.last_close > 0,
        TickerAnalytics.avg_volume_20.isnot(None),
        TickerAnalytics.avg_volume_20 > 0,
        TickerAnalytics.avg_volume_20 * TickerAnalytics.last_close / 1e6 >= _MIN_ADTV_MN,
        func.coalesce(TickerAnalytics.market_cap_mn, 0) >= _MIN_MCAP_MN,
        or_(
            TickerAnalytics.free_float_cap_mn.is_(None),
            TickerAnalytics.free_float_cap_mn >= _MIN_FREE_FLOAT_CAP_MN,
        ),
    )


def _investable_codes(market: str):
    return select(TickerAnalytics.code).where(
        TickerAnalytics.market == market,
        TickerAnalytics.code.in_(_screenable_codes(market)),
        _liquid_universe(),
    )


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


def evening_bodies(d: cards.EveningWrapData) -> dict[str, str]:
    """Bilingual wrap prose, one entry per locale (for the in-app feed note)."""
    dsex = "—" if d.dsex is None else f"{d.dsex:,.0f}"
    chg = "" if d.dsex_change is None else f" ({d.dsex_change:+.2f}%)"
    turnover = "" if d.turnover_cr is None else f" · টার্নওভার Tk {d.turnover_cr:,.0f} কোটি"
    turnover_en = "" if d.turnover_cr is None else f" · turnover Tk {d.turnover_cr:,.0f} cr"
    gainers = _movers_str(d.movers)
    losers = _movers_str(d.losers)
    return {
        "bn": (
            f"🌙 ইভিনিং র‍্যাপ — {d.date_label}\n"
            f"DSEX {dsex}{chg} · {d.advancers}টি বেড়েছে, {d.decliners}টি কমেছে{turnover}।\n"
            f"শীর্ষ গেইনার: {gainers} · শীর্ষ লুজার: {losers}।\n{_NO_ADVICE_BN}"
        ),
        "en": (
            f"🌙 Evening Wrap — {d.date_label}\n"
            f"DSEX {dsex}{chg} · {d.advancers} up, {d.decliners} down{turnover_en}.\n"
            f"Top gainers: {gainers} · top losers: {losers}.\n{_NO_ADVICE_EN}"
        ),
    }


def evening_caption(d: cards.EveningWrapData) -> str:
    """Combined bilingual caption + link (for the Facebook post)."""
    b = evening_bodies(d)
    return f"{b['bn']}\n\n{b['en']}\n\n{_market_cta('evening_wrap')}"


async def build_evening_data(session, market: str) -> tuple[cards.EveningWrapData, str]:
    """Fetch market data → (EveningWrapData, ref_date). Shared by the FB card + the feed note."""
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
    investable = _investable_codes(market)
    gainer_rows = (
        await session.execute(
            select(QuoteSnapshot.code, QuoteSnapshot.change_pct)
            .where(
                QuoteSnapshot.market == market,
                QuoteSnapshot.code.in_(investable),
                QuoteSnapshot.ltp > 0,
                QuoteSnapshot.change_pct > 0,
            )
            .order_by(QuoteSnapshot.change_pct.desc())
            .limit(3)
        )
    ).all()
    loser_rows = (
        await session.execute(
            select(QuoteSnapshot.code, QuoteSnapshot.change_pct)
            .where(
                QuoteSnapshot.market == market,
                QuoteSnapshot.code.in_(investable),
                QuoteSnapshot.ltp > 0,
                QuoteSnapshot.change_pct < 0,
            )
            .order_by(QuoteSnapshot.change_pct.asc())
            .limit(3)
        )
    ).all()
    movers = [cards.Mover(code=c, change_pct=p or 0.0) for c, p in gainer_rows]
    losers = [cards.Mover(code=c, change_pct=p or 0.0) for c, p in loser_rows]

    data = cards.EveningWrapData(
        date_label=summary.date.strftime("%d %b %Y"),
        dsex=summary.dsex,
        dsex_change=index_pct(summary.dsex, summary.dsex_change),
        advancers=adv or 0,
        decliners=dec or 0,
        unchanged=flat or 0,
        turnover_cr=(summary.total_value_mn / 10) if summary.total_value_mn else None,
        movers=movers,
        losers=losers,
    )
    return data, str(summary.date)


async def compose_evening_wrap(session, market: str) -> ComposedPost:
    data, ref_date = await build_evening_data(session, market)
    return ComposedPost(
        kind="evening_wrap",
        ref_date=ref_date,
        caption=evening_caption(data),
        png=cards.evening_wrap_card(data),
        link=_campaign_link("evening_wrap"),
    )


# --- Morning Watch (FB only) -------------------------------------------------
def _codes_str(codes: list[str]) -> str:
    return ", ".join(f"${c}" for c in codes) or "—"


async def _top_codes(session, market: str, col, *, where=None, asc: bool = False, limit: int = 3):
    stmt = select(TickerAnalytics.code, col).where(
        TickerAnalytics.market == market,
        TickerAnalytics.code.in_(_screenable_codes(market)),
        col.isnot(None),
        _liquid_universe(),
    )
    if where is not None:
        stmt = stmt.where(where)
    stmt = stmt.order_by(col.asc() if asc else col.desc()).limit(limit)
    return (await session.execute(stmt)).all()


def _watch_items(rows, value_fmt, unit: str) -> list[tuple[str, str, str]]:
    return [(c, value_fmt(v), unit) for c, v in rows]


async def compose_morning_watch(session, market: str) -> ComposedPost:
    summary = await session.scalar(
        select(MarketSummary)
        .where(MarketSummary.market == market)
        .order_by(MarketSummary.date.desc())
        .limit(1)
    )
    near = await _top_codes(
        session,
        market,
        TickerAnalytics.pct_from_52w_high,
        where=TickerAnalytics.pct_from_52w_high >= -5,
    )
    low = await _top_codes(
        session,
        market,
        TickerAnalytics.pct_from_52w_low,
        where=TickerAnalytics.pct_from_52w_low <= 5,
        asc=True,
    )
    mom = await _top_codes(
        session, market, TickerAnalytics.mom_3_1, where=TickerAnalytics.mom_3_1 > 0
    )
    vol = await _top_codes(
        session, market, TickerAnalytics.rel_volume_5d, where=TickerAnalytics.rel_volume_5d > 1.2
    )
    groups = [
        cards.WatchGroup(
            "NEAR 52W HIGH",
            "Close within 5% of high",
            "high",
            _watch_items(near, lambda p: f"{p:.1f}%", "from high"),
        ),
        cards.WatchGroup(
            "NEAR 52W LOW",
            "Close within 5% of low",
            "low",
            _watch_items(low, lambda p: f"{p:.1f}%", "from low"),
        ),
        cards.WatchGroup(
            "MOMENTUM",
            "3M trend, last month skipped",
            "momentum",
            _watch_items(mom, lambda m: f"{m:+.0f}%", "3M"),
        ),
        cards.WatchGroup(
            "HEAVY VOLUME",
            "5D volume vs 60D avg",
            "volume",
            _watch_items(vol, lambda v: f"{v:.1f}x", "5D/60D"),
        ),
    ]
    today = to_market_tz(dt.datetime.now(dt.UTC)).date()
    dsex = "—" if summary is None or summary.dsex is None else f"{summary.dsex:,.0f}"
    chg = None if summary is None else index_pct(summary.dsex, summary.dsex_change)
    chg_txt = "" if chg is None else f" ({chg:+.2f}%)"
    data = cards.MorningWatchData(
        date_label=today.strftime("%d %b %Y"),
        dsex=summary.dsex if summary else None,
        dsex_change=chg,
        groups=groups,
    )
    nh, ll, mm, vv = (_codes_str([c for c, _ in g]) for g in (near, low, mom, vol))
    caption = (
        f"🌅 মর্নিং ওয়াচ — {data.date_label}\n"
        f"গত ক্লোজে DSEX {dsex}{chg_txt}।\n"
        f"আজকের ডেটা-রাডার — চূড়ার কাছে: {nh} · তলানির কাছে: {ll} · "
        f"মোমেন্টাম: {mm} · বেশি ভলিউম: {vv}।\n{_NO_ADVICE_BN}\n\n"
        f"🌅 Morning Watch — {data.date_label}\n"
        f"At last close DSEX {dsex}{chg_txt}.\n"
        f"Data radar — near highs: {nh} · near lows: {ll} · momentum: {mm} · "
        f"heavy volume: {vv}.\n{_NO_ADVICE_EN}\n\n"
        f"{_market_cta('morning_watch')}"
    )
    return ComposedPost(
        "morning_watch",
        str(today),
        caption,
        cards.morning_watch_card(data),
        _campaign_link("morning_watch"),
    )


# --- Weekly Recap (FB only) --------------------------------------------------
async def compose_weekly_recap(session, market: str) -> ComposedPost:
    latest = await session.scalar(select(func.max(DailyBar.date)).where(DailyBar.market == market))
    if latest is None:
        raise cards.CardError("no daily bars available")
    cutoff = latest - dt.timedelta(days=8)
    vis = visible_codes(market)
    rows = (
        await session.execute(
            select(DailyBar.code, DailyBar.date, DailyBar.close)
            .where(DailyBar.market == market, DailyBar.code.in_(vis), DailyBar.date >= cutoff)
            .order_by(DailyBar.code, DailyBar.date)
        )
    ).all()
    first: dict[str, float] = {}
    last: dict[str, float] = {}
    first_date = latest
    for code, d, close in rows:
        if close is None or close <= 0:
            continue
        if code not in first:
            first[code] = close
        last[code] = close
        first_date = min(first_date, d)
    pcts = {c: (last[c] - first[c]) / first[c] * 100 for c in first if c in last and first[c] > 0}
    ranked = sorted(pcts.items(), key=lambda kv: kv[1], reverse=True)
    gainers = [cards.Mover(c, p) for c, p in ranked[:3]]
    losers = [cards.Mover(c, p) for c, p in ranked[-3:][::-1]]

    # DSEX week change
    dsex_rows = (
        (
            await session.execute(
                select(MarketSummary.dsex)
                .where(MarketSummary.market == market, MarketSummary.date >= cutoff)
                .order_by(MarketSummary.date)
            )
        )
        .scalars()
        .all()
    )
    week_pct = None
    if len(dsex_rows) >= 2 and dsex_rows[0]:
        week_pct = (dsex_rows[-1] - dsex_rows[0]) / dsex_rows[0] * 100

    # leading / lagging sector (>= 3 names)
    sectors = dict(
        (
            await session.execute(select(Symbol.code, Symbol.sector).where(Symbol.market == market))
        ).all()
    )
    by_sector: dict[str, list[float]] = {}
    for c, p in pcts.items():
        sec = sectors.get(c)
        if sec:
            by_sector.setdefault(sec, []).append(p)
    sec_avg = {s: sum(v) / len(v) for s, v in by_sector.items() if len(v) >= 3}
    lead = max(sec_avg, key=sec_avg.get) if sec_avg else None
    lag = min(sec_avg, key=sec_avg.get) if sec_avg else None

    range_label = f"{first_date.strftime('%d')}-{latest.strftime('%d %b %Y')}"
    data = cards.WeeklyRecapData(range_label, week_pct, gainers, losers, lead, lag)
    g = ", ".join(f"${m.code} {m.change_pct:+.0f}%" for m in gainers)
    li = ", ".join(f"${m.code} {m.change_pct:+.0f}%" for m in losers)
    wk = "—" if week_pct is None else f"{week_pct:+.2f}%"
    caption = (
        f"📅 সপ্তাহের সারসংক্ষেপ — {range_label}\n"
        f"এই সপ্তাহে DSEX {wk}।\nশীর্ষ গেইনার: {g}।\nশীর্ষ লুজার: {li}।\n{_NO_ADVICE_BN}\n\n"
        f"📅 Week in Review — {range_label}\n"
        f"DSEX {wk} on the week.\nTop gainers: {g}.\nTop losers: {li}.\n{_NO_ADVICE_EN}\n\n"
        f"{_market_cta('weekly_recap')}"
    )
    return ComposedPost(
        "weekly_recap",
        str(latest),
        caption,
        cards.weekly_recap_card(data),
        _campaign_link("weekly_recap"),
    )


# --- Earnings This Week --------------------------------------------------------
_WEEKDAY_SHORT = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
_MONTH_SHORT = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def _day_label(d: dt.date) -> str:
    return f"{_WEEKDAY_SHORT[d.weekday()]} {d.day} {_MONTH_SHORT[d.month - 1]}"


async def compose_earnings_week(session, market: str) -> ComposedPost:
    """Sunday-morning logo calendar: who reports this week (board meetings on financials),
    Earnings-Whispers style. Skips (CardError) when the week is empty — no filler posts."""
    today = dt.datetime.now(dt.UTC).date()
    until = today + dt.timedelta(days=6)
    meeting_date = Announcement.details["meeting_date"].astext
    rows = list(
        await session.scalars(
            select(Announcement)
            .where(
                Announcement.market == market,
                Announcement.category == "board_meeting",
                meeting_date >= today.isoformat(),
                meeting_date <= until.isoformat(),
            )
            .order_by(meeting_date.asc(), Announcement.strength.desc())
        )
    )
    by_code: dict[str, Announcement] = {}
    for a in rows:
        if (a.details or {}).get("financials") is not False and a.code not in by_code:
            by_code[a.code] = a
    if not by_code:
        raise cards.CardError("no earnings scheduled this week")

    # Logos for every code in one query; missing/failed rows fall back to the card's monogram.
    # librsvg rasterises only PNG/JPEG inside <image> — an .ico/.webp logo would render as a
    # blank white square, so anything else falls back to the card's monogram.
    logos = {
        lg.code: lg
        for lg in await session.scalars(
            select(CompanyLogo).where(
                CompanyLogo.market == market,
                CompanyLogo.code.in_(list(by_code)),
                CompanyLogo.status == "ok",
            )
        )
        if lg.image and (lg.content_type or "") in ("image/png", "image/jpeg")
    }
    by_day: dict[str, list[cards.EarningsEntry]] = {}
    for code, a in sorted(by_code.items(), key=lambda kv: (kv[1].details or {})["meeting_date"]):
        lg = logos.get(code)
        by_day.setdefault((a.details or {})["meeting_date"], []).append(
            cards.EarningsEntry(
                code=code,
                logo_b64=base64.b64encode(lg.image).decode() if lg else None,
                logo_type=(lg.content_type if lg and lg.content_type else "image/png"),
            )
        )
    days = [
        cards.EarningsDay(label=_day_label(dt.date.fromisoformat(day)), items=items)
        for day, items in sorted(by_day.items())
    ][:5]
    first = dt.date.fromisoformat(min(by_day))
    last = dt.date.fromisoformat(max(by_day))
    date_label = f"{first.day}–{last.day} {_MONTH_SHORT[last.month - 1]} {last.year}"

    total = len(by_code)
    caption = (
        f"📅 এ সপ্তাহের আয় — {total}টি কোম্পানির বোর্ড সভা এই সপ্তাহে (আর্থিক ফলাফল)।\n"
        f"তারিখ DSE ঘোষণা অনুযায়ী — বোর্ড পুনঃনির্ধারণ করতে পারে।\n"
        f"📅 Earnings this week — {total} companies report. "
        f"Dates per DSE announcements; boards can reschedule.\n"
        f"{_NO_ADVICE_BN}\n\n{_market_cta('earnings_week')}"
    )
    return ComposedPost(
        kind="earnings_week",
        ref_date=today.isoformat(),
        caption=caption,
        png=cards.earnings_week_card(cards.EarningsWeekData(date_label=date_label, days=days)),
        link=_campaign_link("earnings_week"),
    )


# --- Dhaka Mood -----------------------------------------------------------------
async def compose_mood_card(session, market: str) -> ComposedPost:
    """Evening prime-time mood gauge. English on the card (librsvg has no Bangla face);
    the bilingual read lives in the caption."""
    from api.routers.market import _mood_inputs  # same package; reuse the one mood pipeline

    from bulls.analytics import build_mood

    mood = build_mood(locale="en", **await _mood_inputs(session, market))
    if mood.score is None:
        raise cards.CardError("mood not computable today")
    mood_bn = build_mood(locale="bn", **await _mood_inputs(session, market))

    summary = await session.scalar(
        select(MarketSummary)
        .where(MarketSummary.market == market)
        .order_by(MarketSummary.date.desc())
        .limit(1)
    )
    adv = await session.scalar(
        select(func.count()).where(QuoteSnapshot.market == market, QuoteSnapshot.change_pct > 0)
    )
    dec = await session.scalar(
        select(func.count()).where(QuoteSnapshot.market == market, QuoteSnapshot.change_pct < 0)
    )
    dsex = summary.dsex if summary else None
    pct = index_pct(dsex, summary.dsex_change if summary else None)
    turnover_cr = (summary.total_value_mn / 10) if summary and summary.total_value_mn else None
    today = dt.datetime.now(dt.UTC).date()

    d = cards.MoodCardData(
        date_label=_day_label(today).title(),
        score=mood.score,
        band_label=mood.label,
        dsex=dsex,
        dsex_change_pct=pct,
        turnover_cr=turnover_cr,
        advancers=adv or 0,
        decliners=dec or 0,
    )
    caption = (
        f"আজকের Dhaka Mood: {mood.score} — {mood_bn.label}। {mood_bn.caption}\n"
        f"Today's Dhaka Mood: {mood.score} — {mood.label}. {mood.caption}\n"
        f"{_NO_ADVICE_BN}\n\n{_market_cta('mood')}"
    )
    return ComposedPost(
        kind="mood",
        ref_date=today.isoformat(),
        caption=caption,
        png=cards.mood_card(d),
        link=_campaign_link("mood"),
    )
