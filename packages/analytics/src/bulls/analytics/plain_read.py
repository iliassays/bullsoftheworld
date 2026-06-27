"""Plain read — turn a symbol's factor row into one human-readable profile.

The screens give a trader 20 accurate numbers and no way to combine them. This synthesises the same
precomputed facts into plain sentences ("large, steady, high-quality, stretched short-term") plus a
"how traders read this profile" framing — so the user can form their OWN view.

Strictly deterministic and templated (no LLM, so no drift), and strictly descriptive: it states what
the data shows and how the profile is generally read, and never says buy or sell. Any factor we don't
have is simply omitted (omit over mislead) rather than guessed.
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
    disclaimer: str = (
        "This describes what the data shows and how such a profile is generally read — "
        "it is not a recommendation. Your decision and your risk are your own."
    )


# Thresholds calibrated to the DSE distribution (volatility p50≈41%, ROE p50≈3%, etc.).
def _size_point(market_cap_mn: float | None, adtv_mn: float | None) -> ReadPoint | None:
    if market_cap_mn is None:
        return None
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


def _trend_point(above_200: bool | None, mom_12_1: float | None) -> ReadPoint | None:
    if above_200 is None and mom_12_1 is None:
        return None
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


def _steadiness_point(volatility: float | None) -> ReadPoint | None:
    if volatility is None:
        return None
    if volatility < 30:
        text = f"It's been unusually steady for this market (volatility ~{volatility:.0f}%)."
    elif volatility > 55:
        text = f"It's very volatile — big day-to-day swings (volatility ~{volatility:.0f}%)."
    else:
        text = f"It has moderate day-to-day swings (volatility ~{volatility:.0f}%)."
    return ReadPoint(tag="steadiness", text=text)


def _quality_point(roe: float | None) -> ReadPoint | None:
    if roe is None:
        return None
    if roe <= 0:
        text = "It's currently lossmaking (negative return on equity)."
    elif roe >= 15:
        text = f"It's highly profitable — strong return on equity (~{roe:.0f}%)."
    elif roe >= 8:
        text = f"It's solidly profitable (return on equity ~{roe:.0f}%)."
    else:
        text = f"Its profitability is modest (return on equity ~{roe:.0f}%)."
    return ReadPoint(tag="quality", text=text)


def _value_point(pe_ratio: float | None, pe_vs_sector: float | None) -> ReadPoint | None:
    if pe_vs_sector is None:
        return None
    if pe_vs_sector < 0.8:
        text = "On earnings it looks cheaper than its sector peers"
    elif pe_vs_sector > 1.2:
        text = "On earnings it looks pricier than its sector peers"
    else:
        text = "On earnings it's priced roughly in line with its sector"
    if pe_ratio is not None and pe_ratio > 0:
        text += f" (P/E ~{pe_ratio:.0f})"
    return ReadPoint(tag="value", text=text + ".")


def _income_point(dividend_yield: float | None) -> ReadPoint | None:
    if dividend_yield is None or dividend_yield <= 0:
        return None
    qualifier = "a healthy" if dividend_yield >= 5 else "a modest"
    return ReadPoint(
        tag="income", text=f"It pays {qualifier} cash dividend (~{dividend_yield:.1f}% at this price)."
    )


def _shortterm_point(
    rsi: float | None, pct_from_high: float | None, pct_from_low: float | None
) -> ReadPoint | None:
    bits: list[str] = []
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


def _flow_point(cmf: float | None) -> ReadPoint | None:
    if cmf is None:
        return None
    if cmf > 0.05:
        return ReadPoint(tag="flow", text="Recent volume shows buyers in control (money flowing in).")
    if cmf < -0.05:
        return ReadPoint(tag="flow", text="Recent volume shows sellers in control (money flowing out).")
    return None


def _smartmoney_point(inst_delta: float | None, foreign_delta: float | None) -> ReadPoint | None:
    combined = (inst_delta or 0) + (foreign_delta or 0)
    if combined >= 1:
        return ReadPoint(
            tag="smartmoney",
            text=f"Institutions/foreign investors added to their stake (+{combined:.1f} pp) at the last disclosure.",
        )
    if combined <= -1:
        return ReadPoint(
            tag="smartmoney",
            text=f"Institutions/foreign investors trimmed their stake ({combined:.1f} pp) at the last disclosure.",
        )
    return None


def _headline(
    above_200: bool | None, volatility: float | None, roe: float | None, rsi: float | None
) -> str:
    traits: list[str] = []
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
    above_200: bool | None, volatility: float | None, roe: float | None, rsi: float | None,
    pe_vs_sector: float | None, dividend_yield: float | None, pct_from_low: float | None,
) -> str:
    lines: list[str] = []
    quality_steady = (roe is not None and roe >= 8) and (volatility is not None and volatility < 35)
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
        lines.append("Income investors would weigh the dividend against how steady the business is.")
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
    candidates = [
        _size_point(market_cap_mn, adtv_mn),
        _trend_point(above_sma_200, mom_12_1),
        _steadiness_point(volatility),
        _quality_point(roe),
        _value_point(pe_ratio, pe_vs_sector),
        _income_point(dividend_yield),
        _flow_point(cmf_20),
        _smartmoney_point(institute_delta, foreign_delta),
        _shortterm_point(rsi_14, pct_from_52w_high, pct_from_52w_low),
    ]
    points = [p for p in candidates if p is not None]
    return PlainRead(
        code=code,
        as_of_date=as_of_date,
        headline=_headline(above_sma_200, volatility, roe, rsi_14),
        points=points,
        how_to_read=_how_to_read(
            above_sma_200, volatility, roe, rsi_14, pe_vs_sector, dividend_yield, pct_from_52w_low
        ),
    )
