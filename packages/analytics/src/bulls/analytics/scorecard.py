"""Stock Scorecard + Red Flags — glanceable, transparent, descriptive per-symbol summaries.

Like plain_read: strictly deterministic and templated (no LLM), strictly descriptive. The Scorecard
rates a symbol on independent 0-10 dimensions (Trend / Quality / Value / Income / Momentum) — there
is deliberately NO single composite score, because one number reads as a buy/sell verdict. Each
dimension carries the metrics behind it (transparency = trust), and any dimension whose inputs are
missing is omitted rather than guessed (omit over mislead). A low Value score means "expensive",
never "avoid".

Red Flags are descriptive risk badges (Z-category, thin liquidity, lossmaking, …) — facts that say
"be careful", never "don't buy". A symbol with none is shown as clean.

Bilingual (EN/BN): interpolated numbers stay Western numerals; surrounding words translate.
"""

from __future__ import annotations

from pydantic import BaseModel


class Dimension(BaseModel):
    key: str  # trend | quality | value | income | momentum
    label: str  # localized
    score: int  # 0..10
    detail: str  # localized metrics behind the score


class Scorecard(BaseModel):
    code: str
    as_of_date: str
    dimensions: list[Dimension]
    disclaimer: str


class RedFlag(BaseModel):
    key: str
    label: str  # localized


class RedFlags(BaseModel):
    code: str
    flags: list[RedFlag]
    clean: bool
    note: str  # localized "not a 'don't buy'" framing


_DIM_LABELS = {
    "trend": ("Trend", "প্রবণতা"),
    "quality": ("Quality", "মান"),
    "value": ("Value", "মূল্য"),
    "income": ("Income", "আয়"),
    "momentum": ("Momentum", "গতি"),
}

_SCORECARD_DISCLAIMER = {
    "en": (
        "Each score shows the data behind it — not a black box. Scores summarise the facts; they "
        "are not buy/sell signals. A low Value score means pricey, not 'avoid'."
    ),
    "bn": (
        "প্রতিটি স্কোর তার ভিত্তি দেখায় — কোনো ব্ল্যাক বক্স নয়। স্কোর তথ্যের সারাংশ, কেনা-বেচার "
        "সংকেত নয়। কম মূল্য-স্কোর মানে দামি, 'এড়িয়ে চলুন' নয়।"
    ),
}

_FLAGS_NOTE = {
    "en": "Red flags aren't 'don't buy' — just facts that say be careful.",
    "bn": "রেড ফ্ল্যাগ মানে 'কিনবেন না' নয় — শুধু তথ্য যা সতর্ক হতে বলে।",
}


def _clamp10(x: float) -> int:
    return int(max(0, min(10, round(x))))


def _label(key: str, bn: bool) -> str:
    return _DIM_LABELS[key][1 if bn else 0]


def _trend(above_200: bool | None, above_50: bool | None, mom_12_1: float | None, bn: bool):
    if above_200 is None and above_50 is None:
        return None
    base = 5.0
    if above_200 is True:
        base += 2
    elif above_200 is False:
        base -= 2
    if above_50 is True:
        base += 1
    elif above_50 is False:
        base -= 1
    if mom_12_1 is not None:
        base += 2 if mom_12_1 >= 50 else 1 if mom_12_1 > 0 else -1 if mom_12_1 < -20 else 0
    if bn:
        d = (
            "200-দিন গড়ের উপরে"
            if above_200
            else "200-দিন গড়ের নিচে"
            if above_200 is False
            else "দীর্ঘমেয়াদি দিকনির্দেশনা"
        )
        if mom_12_1 is not None:
            d += f" · 12-মাস {mom_12_1:+.0f}%"
    else:
        d = (
            "Above 200-DMA"
            if above_200
            else "Below 200-DMA"
            if above_200 is False
            else "Long-term direction"
        )
        if mom_12_1 is not None:
            d += f" · 12m {mom_12_1:+.0f}%"
    return Dimension(key="trend", label=_label("trend", bn), score=_clamp10(base), detail=d)


def _quality(roe: float | None, bn: bool):
    if roe is None:
        return None
    score = (
        1
        if roe <= 0
        else 3
        if roe < 5
        else 5
        if roe < 8
        else 7
        if roe < 15
        else 8
        if roe < 20
        else 10
    )
    d = f"ROE {roe:.0f}%"
    return Dimension(key="quality", label=_label("quality", bn), score=score, detail=d)


def _value(pe_vs_sector: float | None, pe_ratio: float | None, bn: bool):
    if pe_vs_sector is None:
        return None
    score = (
        9
        if pe_vs_sector < 0.7
        else 7
        if pe_vs_sector < 0.9
        else 5
        if pe_vs_sector < 1.1
        else 3
        if pe_vs_sector < 1.4
        else 2
    )
    if bn:
        d = f"খাতের {pe_vs_sector:.1f}x"
        if pe_ratio is not None and pe_ratio > 0:
            d += f" · পি/ই {pe_ratio:.0f}"
    else:
        d = f"{pe_vs_sector:.1f}x sector"
        if pe_ratio is not None and pe_ratio > 0:
            d += f" · P/E {pe_ratio:.0f}"
    return Dimension(key="value", label=_label("value", bn), score=score, detail=d)


def _income(dividend_yield: float | None, bn: bool):
    # No dividend isn't a low score — it's simply not an income stock. Omit rather than penalise.
    if dividend_yield is None or dividend_yield <= 0:
        return None
    score = (
        10 if dividend_yield >= 8 else 8 if dividend_yield >= 5 else 6 if dividend_yield >= 3 else 4
    )
    d = f"ইল্ড {dividend_yield:.1f}%" if bn else f"Yield {dividend_yield:.1f}%"
    return Dimension(key="income", label=_label("income", bn), score=score, detail=d)


def _momentum(rsi_14: float | None, mom_6_1: float | None, mom_3_1: float | None, bn: bool):
    mom = mom_6_1 if mom_6_1 is not None else mom_3_1
    if mom is None and rsi_14 is None:
        return None
    if mom is None:
        score = 5
    else:
        score = 9 if mom >= 30 else 7 if mom >= 10 else 6 if mom > 0 else 4 if mom > -10 else 2
    bits = []
    if rsi_14 is not None:
        bits.append(f"RSI {rsi_14:.0f}")
    if mom is not None:
        bits.append(
            (f"6-মাস {mom:+.0f}%" if mom_6_1 is not None else f"3-মাস {mom:+.0f}%")
            if bn
            else (f"6m {mom:+.0f}%" if mom_6_1 is not None else f"3m {mom:+.0f}%")
        )
    return Dimension(
        key="momentum", label=_label("momentum", bn), score=score, detail=" · ".join(bits)
    )


def build_scorecard(
    *,
    code: str,
    as_of_date: str,
    locale: str = "en",
    above_sma_200: bool | None = None,
    above_sma_50: bool | None = None,
    mom_12_1: float | None = None,
    mom_6_1: float | None = None,
    mom_3_1: float | None = None,
    rsi_14: float | None = None,
    roe: float | None = None,
    pe_ratio: float | None = None,
    pe_vs_sector: float | None = None,
    dividend_yield: float | None = None,
) -> Scorecard:
    """Rate the symbol on independent 0-10 dimensions. Dimensions with no data are omitted."""
    bn = locale == "bn"
    candidates = [
        _trend(above_sma_200, above_sma_50, mom_12_1, bn),
        _quality(roe, bn),
        _value(pe_vs_sector, pe_ratio, bn),
        _income(dividend_yield, bn),
        _momentum(rsi_14, mom_6_1, mom_3_1, bn),
    ]
    return Scorecard(
        code=code,
        as_of_date=as_of_date,
        dimensions=[d for d in candidates if d is not None],
        disclaimer=_SCORECARD_DISCLAIMER["bn" if bn else "en"],
    )


def build_red_flags(
    *,
    code: str,
    locale: str = "en",
    category: str | None = None,
    adtv_mn: float | None = None,
    roe: float | None = None,
    dividend_yield: float | None = None,
    free_float_cap_mn: float | None = None,
    today_change_pct: float | None = None,
) -> RedFlags:
    """Descriptive risk badges. Only flags we can stand behind from the data; clean when none fire."""
    bn = locale == "bn"
    flags: list[RedFlag] = []

    def add(key: str, en: str, bnt: str):
        flags.append(RedFlag(key=key, label=bnt if bn else en))

    if category == "Z":
        add("z_category", "Z category", "Z-ক্যাটাগরি")
    if adtv_mn is not None and adtv_mn < 2:
        add("thin", "Thinly traded", "কম লেনদেন")
    if roe is not None and roe <= 0:
        add("lossmaking", "Loss-making", "লোকসানে")
    if free_float_cap_mn is not None and free_float_cap_mn < 100:
        add("tiny_float", "Tiny free float", "খুব কম ফ্রি ফ্লোট")
    if today_change_pct is not None and abs(today_change_pct) >= 9.7:
        add("circuit", "Circuit-locked today", "আজ সার্কিটে আটকে")

    return RedFlags(
        code=code,
        flags=flags,
        clean=not flags,
        note=_FLAGS_NOTE["bn" if bn else "en"],
    )
