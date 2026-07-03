"""Plain read — turn a symbol's factor row into one human-readable profile.

The screens give a trader 20 accurate numbers and no way to combine them. This synthesises the same
precomputed facts into plain sentences ("large, steady, high-quality, stretched short-term") plus a
"how traders read this profile" framing — so the user can form their OWN view.

Strictly deterministic and templated (no LLM, so no drift), and strictly descriptive: it states what
the data shows and how the profile is generally read, and never says buy or sell. Any factor we don't
have is simply omitted (omit over mislead) rather than guessed.

Bilingual (EN/BN): interpolated numbers stay Western numerals (matching the other deterministic
templates); the surrounding words are translated. `locale="bn"` selects Bangla.
"""

from __future__ import annotations

from pydantic import BaseModel


class ReadPoint(BaseModel):
    tag: str  # size | trend | steadiness | quality | value | income | shortterm | flow | smartmoney
    text: str


class PlainRead(BaseModel):
    code: str
    as_of_date: str
    headline: str
    points: list[ReadPoint]
    how_to_read: str
    disclaimer: str


_DISCLAIMER = {
    "en": (
        "This describes what the data shows and how such a profile is generally read — "
        "it is not a recommendation. Your decision and your risk are your own."
    ),
    "bn": (
        "এটি কেবল তথ্য কী দেখায় এবং এমন একটি প্রোফাইল সাধারণত কীভাবে পড়া হয় তা বর্ণনা করে — "
        "এটি কোনো সুপারিশ নয়। সিদ্ধান্ত ও ঝুঁকি আপনার নিজের।"
    ),
}


# Thresholds calibrated to the DSE distribution (volatility p50≈41%, ROE p50≈3%, etc.).
def _size_point(market_cap_mn: float | None, adtv_mn: float | None, bn: bool) -> ReadPoint | None:
    if market_cap_mn is None:
        return None
    if bn:
        size = (
            "একটি বড় কোম্পানি"
            if market_cap_mn >= 5000
            else "একটি ছোট কোম্পানি"
            if market_cap_mn < 1000
            else "একটি মাঝারি আকারের কোম্পানি"
        )
        liq = ""
        if adtv_mn is not None:
            liq = (
                ", খুব বেশি লেনদেন হয় (সহজে ঢোকা-বেরোনো যায়)"
                if adtv_mn >= 20
                else ", কম লেনদেন হয় (ঢোকা-বেরোনো কঠিন)"
                if adtv_mn < 2
                else ", ঢোকা-বেরোনোর মতো যথেষ্ট লেনদেন হয়"
            )
        return ReadPoint(tag="size", text=f"এটি {size}{liq}।")
    if market_cap_mn >= 5000:
        size = "a large company"
    elif market_cap_mn < 1000:
        size = "a small company"
    else:
        size = "a mid-sized company"
    liq = ""
    if adtv_mn is not None:
        if adtv_mn >= 20:
            liq = ", very heavily traded (easy to get in and out)"
        elif adtv_mn < 2:
            liq = ", thinly traded (harder to get in and out)"
        else:
            liq = ", traded actively enough to enter and exit"
    return ReadPoint(tag="size", text=f"It's {size}{liq}.")


def _trend_point(above_200: bool | None, mom_12_1: float | None, bn: bool) -> ReadPoint | None:
    if above_200 is None and mom_12_1 is None:
        return None
    if bn:
        if above_200 is True:
            base = "এর দীর্ঘমেয়াদি প্রবণতা ঊর্ধ্বমুখী — ২০০-দিনের গড় দামের উপরে লেনদেন হচ্ছে"
        elif above_200 is False:
            base = "এর দীর্ঘমেয়াদি প্রবণতা নিম্নমুখী — ২০০-দিনের গড় দামের নিচে লেনদেন হচ্ছে"
        else:
            base = "এর দীর্ঘমেয়াদি দিকনির্দেশনা"
        if mom_12_1 is not None and mom_12_1 >= 50:
            base += f", এবং এটি ১২ মাসে শক্তিশালী লাভকারী (বছরে প্রায় {mom_12_1:.0f}%)"
        elif mom_12_1 is not None and mom_12_1 <= -20:
            base += f", এবং বছরে বেশ নিচে নেমেছে (প্রায় {mom_12_1:.0f}%)"
        return ReadPoint(tag="trend", text=base + "।")
    if above_200 is True:
        base = "Its long-term trend is up — trading above its 200-day average price"
    elif above_200 is False:
        base = "Its long-term trend is down — trading below its 200-day average price"
    else:
        base = "Its longer-term direction"
    if mom_12_1 is not None and mom_12_1 >= 50:
        base += f", and it's a strong 12-month gainer (about {mom_12_1:.0f}% over the year)"
    elif mom_12_1 is not None and mom_12_1 <= -20:
        base += f", and it's well down over the year (about {mom_12_1:.0f}%)"
    return ReadPoint(tag="trend", text=base + ".")


def _steadiness_point(volatility: float | None, bn: bool) -> ReadPoint | None:
    if volatility is None:
        return None
    if bn:
        if volatility < 30:
            text = f"এই বাজারের তুলনায় এটি অস্বাভাবিকভাবে স্থির ছিল (অস্থিরতা ~{volatility:.0f}%)।"
        elif volatility > 55:
            text = f"এটি খুব অস্থির — দৈনিক বড় ওঠানামা (অস্থিরতা ~{volatility:.0f}%)।"
        else:
            text = f"এর দৈনিক ওঠানামা মাঝারি (অস্থিরতা ~{volatility:.0f}%)।"
        return ReadPoint(tag="steadiness", text=text)
    if volatility < 30:
        text = f"It's been unusually steady for this market (volatility ~{volatility:.0f}%)."
    elif volatility > 55:
        text = f"It's very volatile — big day-to-day swings (volatility ~{volatility:.0f}%)."
    else:
        text = f"It has moderate day-to-day swings (volatility ~{volatility:.0f}%)."
    return ReadPoint(tag="steadiness", text=text)


def _quality_point(roe: float | None, bn: bool) -> ReadPoint | None:
    if roe is None:
        return None
    if bn:
        if roe <= 0:
            text = "এটি বর্তমানে লোকসানে (নেতিবাচক রিটার্ন অন ইকুইটি)।"
        elif roe >= 15:
            text = f"এটি অত্যন্ত লাভজনক — শক্তিশালী রিটার্ন অন ইকুইটি (~{roe:.0f}%)।"
        elif roe >= 8:
            text = f"এটি ভালোভাবে লাভজনক (রিটার্ন অন ইকুইটি ~{roe:.0f}%)।"
        else:
            text = f"এর লাভজনকতা সামান্য (রিটার্ন অন ইকুইটি ~{roe:.0f}%)।"
        return ReadPoint(tag="quality", text=text)
    if roe <= 0:
        text = "It's currently lossmaking (negative return on equity)."
    elif roe >= 15:
        text = f"It's highly profitable — strong return on equity (~{roe:.0f}%)."
    elif roe >= 8:
        text = f"It's solidly profitable (return on equity ~{roe:.0f}%)."
    else:
        text = f"Its profitability is modest (return on equity ~{roe:.0f}%)."
    return ReadPoint(tag="quality", text=text)


def _value_point(pe_ratio: float | None, pe_vs_sector: float | None, bn: bool) -> ReadPoint | None:
    if pe_vs_sector is None:
        return None
    if bn:
        if pe_vs_sector < 0.8:
            text = "আয়ের বিচারে এটি তার খাতের সমকক্ষদের চেয়ে সস্তা মনে হচ্ছে"
        elif pe_vs_sector > 1.2:
            text = "আয়ের বিচারে এটি তার খাতের সমকক্ষদের চেয়ে দামি মনে হচ্ছে"
        else:
            text = "আয়ের বিচারে এটি মোটামুটি তার খাতের সমান দামে আছে"
        if pe_ratio is not None and pe_ratio > 0:
            text += f" (পি/ই ~{pe_ratio:.0f})"
        return ReadPoint(tag="value", text=text + "।")
    if pe_vs_sector < 0.8:
        text = "On earnings it looks cheaper than its sector peers"
    elif pe_vs_sector > 1.2:
        text = "On earnings it looks pricier than its sector peers"
    else:
        text = "On earnings it's priced roughly in line with its sector"
    if pe_ratio is not None and pe_ratio > 0:
        text += f" (P/E ~{pe_ratio:.0f})"
    return ReadPoint(tag="value", text=text + ".")


def _income_point(dividend_yield: float | None, bn: bool) -> ReadPoint | None:
    if dividend_yield is None or dividend_yield <= 0:
        return None
    if bn:
        q = "ভালো" if dividend_yield >= 5 else "সামান্য"
        return ReadPoint(
            tag="income",
            text=f"এটি {q} নগদ লভ্যাংশ দেয় (এই দামে ~{dividend_yield:.1f}%)।",
        )
    qualifier = "a healthy" if dividend_yield >= 5 else "a modest"
    return ReadPoint(
        tag="income",
        text=f"It pays {qualifier} cash dividend (~{dividend_yield:.1f}% at this price).",
    )


def _shortterm_point(
    rsi: float | None, pct_from_high: float | None, pct_from_low: float | None, bn: bool
) -> ReadPoint | None:
    bits: list[str] = []
    if bn:
        if rsi is not None and rsi >= 70:
            bits.append(f"দৌড়ের পর স্বল্পমেয়াদে এটি বেশি বেড়ে গেছে বলে মনে হচ্ছে (RSI {rsi:.0f})")
        elif rsi is not None and rsi <= 30:
            bits.append(f"পতনের পর স্বল্পমেয়াদে এটি অনেক নিচে নেমেছে বলে মনে হচ্ছে (RSI {rsi:.0f})")
        if pct_from_high is not None and pct_from_high >= -5:
            bits.append("এটি ৫২-সপ্তাহের সর্বোচ্চের কাছে")
        elif pct_from_low is not None and pct_from_low <= 5:
            bits.append("এটি ৫২-সপ্তাহের সর্বনিম্নের কাছে")
        if not bits:
            return None
        return ReadPoint(tag="shortterm", text="এই মুহূর্তে " + ", এবং ".join(bits) + "।")
    if rsi is not None and rsi >= 70:
        bits.append(f"it looks stretched short-term (RSI {rsi:.0f}) after running up")
    elif rsi is not None and rsi <= 30:
        bits.append(f"it looks beaten down short-term (RSI {rsi:.0f}) after falling")
    if pct_from_high is not None and pct_from_high >= -5:
        bits.append("it's near its 52-week high")
    elif pct_from_low is not None and pct_from_low <= 5:
        bits.append("it's near its 52-week low")
    if not bits:
        return None
    return ReadPoint(tag="shortterm", text="Right now " + ", and ".join(bits) + ".")


def _flow_point(cmf: float | None, bn: bool) -> ReadPoint | None:
    if cmf is None:
        return None
    if cmf > 0.05:
        text = (
            "সাম্প্রতিক ভলিউমে ক্রেতারা নিয়ন্ত্রণে (অর্থ ঢুকছে)।"
            if bn
            else "Recent volume shows buyers in control (money flowing in)."
        )
        return ReadPoint(tag="flow", text=text)
    if cmf < -0.05:
        text = (
            "সাম্প্রতিক ভলিউমে বিক্রেতারা নিয়ন্ত্রণে (অর্থ বেরোচ্ছে)।"
            if bn
            else "Recent volume shows sellers in control (money flowing out)."
        )
        return ReadPoint(tag="flow", text=text)
    return None


def _smartmoney_point(
    inst_delta: float | None, foreign_delta: float | None, bn: bool
) -> ReadPoint | None:
    combined = (inst_delta or 0) + (foreign_delta or 0)
    if combined >= 1:
        text = (
            f"শেষ প্রকাশে প্রতিষ্ঠান/বিদেশি বিনিয়োগকারীরা তাদের অংশ বাড়িয়েছে (+{combined:.1f} pp)।"
            if bn
            else f"Institutions/foreign investors added to their stake (+{combined:.1f} pp) at the last disclosure."
        )
        return ReadPoint(tag="smartmoney", text=text)
    if combined <= -1:
        text = (
            f"শেষ প্রকাশে প্রতিষ্ঠান/বিদেশি বিনিয়োগকারীরা তাদের অংশ কমিয়েছে ({combined:.1f} pp)।"
            if bn
            else f"Institutions/foreign investors trimmed their stake ({combined:.1f} pp) at the last disclosure."
        )
        return ReadPoint(tag="smartmoney", text=text)
    return None


def _headline(
    above_200: bool | None, volatility: float | None, roe: float | None, rsi: float | None, bn: bool
) -> str:
    if bn:
        traits: list[str] = []
        if roe is not None and roe >= 15:
            traits.append("উচ্চ-মানের")
        if volatility is not None and volatility < 30:
            traits.append("স্থির")
        if above_200 is True:
            traits.append("দীর্ঘমেয়াদি ঊর্ধ্বমুখী প্রবণতায়")
        elif above_200 is False:
            traits.append("দীর্ঘমেয়াদি নিম্নমুখী প্রবণতায়")
        if not traits:
            traits.append("একটি মিশ্র প্রোফাইল")
        head = ", ".join(traits[:-1]) + (" এবং " if len(traits) > 1 else "") + traits[-1]
        if rsi is not None and rsi >= 70:
            head += " — তবে স্বল্পমেয়াদে বেশি বেড়ে গেছে"
        elif rsi is not None and rsi <= 30:
            head += " — এবং স্বল্পমেয়াদে অনেক নিচে"
        return head + "।"
    traits = []
    if roe is not None and roe >= 15:
        traits.append("high-quality")
    if volatility is not None and volatility < 30:
        traits.append("steady")
    if above_200 is True:
        traits.append("in a long-term uptrend")
    elif above_200 is False:
        traits.append("in a long-term downtrend")
    if not traits:
        traits.append("a mixed profile")
    head = ", ".join(traits[:-1]) + (" and " if len(traits) > 1 else "") + traits[-1]
    if rsi is not None and rsi >= 70:
        head += " — but stretched short-term"
    elif rsi is not None and rsi <= 30:
        head += " — and beaten down short-term"
    return head[0].upper() + head[1:] + "."


def _how_to_read(
    above_200: bool | None,
    volatility: float | None,
    roe: float | None,
    rsi: float | None,
    pe_vs_sector: float | None,
    dividend_yield: float | None,
    pct_from_low: float | None,
    bn: bool,
) -> str:
    lines: list[str] = []
    quality_steady = (roe is not None and roe >= 8) and (volatility is not None and volatility < 35)
    if bn:
        if quality_steady and above_200 is True:
            lines.append(
                "মান, স্থিরতা ও ঊর্ধ্বমুখী প্রবণতা — দীর্ঘমেয়াদি বিনিয়োগকারীরা সাধারণত এই প্রোফাইল পছন্দ করেন।"
            )
        if pe_vs_sector is not None and pe_vs_sector < 0.8 and (roe is not None and roe > 0):
            lines.append(
                "লাভজনক কোম্পানি সমকক্ষদের চেয়ে সস্তা — এটাই ভ্যালু বিনিয়োগকারীরা খোঁজেন; তবে 'সস্তা' "
                "মানে বাজার কোনো সমস্যা দেখছে এমনও হতে পারে, তাই কারণ যাচাই করুন।"
            )
        if dividend_yield is not None and dividend_yield >= 5:
            lines.append("আয়-সন্ধানী বিনিয়োগকারীরা লভ্যাংশকে ব্যবসার স্থিতিশীলতার সাথে বিবেচনা করবেন।")
        if rsi is not None and rsi >= 70:
            lines.append("দ্রুত বেড়ে যাওয়ায় অনেক ট্রেডার পিছনে না ছুটে শান্ত একটি পুলব্যাকের অপেক্ষা করেন।")
        elif rsi is not None and rsi <= 30 and pct_from_low is not None and pct_from_low <= 5:
            lines.append(
                "৫২-সপ্তাহের সর্বনিম্নের কাছে পড়ে থাকা একটি বাউন্স সেটআপ হতে পারে, আবার পড়ন্ত ছুরিও হতে "
                "পারে — ট্রেডাররা সাধারণত দাম পড়া থামার অপেক্ষা করেন এবং আগে খবর যাচাই করেন।"
            )
        if not lines:
            lines.append(
                "এখানে একক কোনো স্পষ্ট সংকেত নেই — ট্রেডাররা কিছু করার আগে এটিকে নিজের লক্ষ্যের "
                "(গ্রোথ, ভ্যালু, আয় বা স্থিরতা) সাথে মিলিয়ে দেখবেন।"
            )
        lines.append("প্রোফাইল যাই হোক, কেন দাম নড়ল (খবর) যাচাই করুন এবং আপনার এন্ট্রি ও ঝুঁকি ঠিক করুন।")
        return " ".join(lines)
    if quality_steady and above_200 is True:
        lines.append(
            "Quality, steady and trending up is the profile longer-term investors tend to favour."
        )
    if pe_vs_sector is not None and pe_vs_sector < 0.8 and (roe is not None and roe > 0):
        lines.append(
            "Cheaper-than-peers on a profitable company is what value investors look for — "
            "though 'cheap' can also mean the market sees a problem, so check why."
        )
    if dividend_yield is not None and dividend_yield >= 5:
        lines.append(
            "Income investors would weigh the dividend against how steady the business is."
        )
    if rsi is not None and rsi >= 70:
        lines.append(
            "Because it's run up fast, many traders watch for a calmer pullback rather than chase it."
        )
    elif rsi is not None and rsi <= 30 and pct_from_low is not None and pct_from_low <= 5:
        lines.append(
            "Beaten-down near a 52-week low can be a bounce setup OR a falling knife — "
            "traders usually wait for the price to stop falling and check the news first."
        )
    if not lines:
        lines.append(
            "There's no single standout signal here — traders would line this up against their own "
            "goal (growth, value, income or steadiness) before doing anything."
        )
    lines.append("Whatever the profile, check why it moved (news) and decide your entry and risk.")
    return " ".join(lines)


def build_plain_read(
    *,
    code: str,
    as_of_date: str,
    locale: str = "en",
    market_cap_mn: float | None = None,
    adtv_mn: float | None = None,
    above_sma_200: bool | None = None,
    mom_12_1: float | None = None,
    volatility: float | None = None,
    roe: float | None = None,
    pe_ratio: float | None = None,
    pe_vs_sector: float | None = None,
    dividend_yield: float | None = None,
    rsi_14: float | None = None,
    pct_from_52w_high: float | None = None,
    pct_from_52w_low: float | None = None,
    cmf_20: float | None = None,
    institute_delta: float | None = None,
    foreign_delta: float | None = None,
) -> PlainRead:
    """Synthesise the factor row into a readable profile. Null factors are omitted."""
    bn = locale == "bn"
    candidates = [
        _size_point(market_cap_mn, adtv_mn, bn),
        _trend_point(above_sma_200, mom_12_1, bn),
        _steadiness_point(volatility, bn),
        _quality_point(roe, bn),
        _value_point(pe_ratio, pe_vs_sector, bn),
        _income_point(dividend_yield, bn),
        _flow_point(cmf_20, bn),
        _smartmoney_point(institute_delta, foreign_delta, bn),
        _shortterm_point(rsi_14, pct_from_52w_high, pct_from_52w_low, bn),
    ]
    points = [p for p in candidates if p is not None]
    return PlainRead(
        code=code,
        as_of_date=as_of_date,
        headline=_headline(above_sma_200, volatility, roe, rsi_14, bn),
        points=points,
        how_to_read=_how_to_read(
            above_sma_200,
            volatility,
            roe,
            rsi_14,
            pe_vs_sector,
            dividend_yield,
            pct_from_52w_low,
            bn,
        ),
        disclaimer=_DISCLAIMER["bn" if bn else "en"],
    )
