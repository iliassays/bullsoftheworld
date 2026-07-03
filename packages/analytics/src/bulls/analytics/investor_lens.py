"""Investor Lens — deterministic persona-style reads over DSE facts.

This borrows the useful part of the ai-hedge-fund idea: different investment styles read the same
stock differently. It deliberately does not emit buy/sell calls, target prices, or a single final
rating. Each lens is a grounded interpretation of the persisted DSE analytics row.
"""

from __future__ import annotations

from itertools import pairwise

from pydantic import BaseModel


class LensCheck(BaseModel):
    """One criterion the style cares about, shown as actual-vs-expected so the reader sees the gap.
    Field names + status values match the web client's declared contract."""

    label: str
    actual: str  # this stock's value, formatted (or "—" if unknown)
    expected: str  # the style's benchmark, plain (e.g. "≤ 15x")
    status: str  # pass | watch | fail | na


class InvestorLens(BaseModel):
    key: str
    name: str
    persona: str
    verdict: str  # supportive | mixed | caution | thin_data
    score: int | None
    summary: str
    points: list[str]
    checks: list[LensCheck] = []  # have-vs-want criteria (fundamental lenses); FE prefers these
    watch_next: list[str]


class InvestorLensResponse(BaseModel):
    code: str
    as_of_date: str
    headline: str
    lenses: list[InvestorLens]
    disclaimer: str


_DISCLAIMER = {
    "en": (
        "Investor Lens shows how different investing styles read the same DSE facts. It is not a "
        "recommendation, price target, or trading signal."
    ),
    "bn": (
        "Investor Lens একই DSE তথ্যকে ভিন্ন বিনিয়োগ-স্টাইল কীভাবে পড়ে তা দেখায়। এটি সুপারিশ, "
        "দাম লক্ষ্যমাত্রা বা ট্রেডিং সিগন্যাল নয়।"
    ),
}


def _clamp10(x: float) -> int:
    return int(max(0, min(10, round(x))))


# --- Persona scorers: the SINGLE SOURCE OF TRUTH for every lens score. -------------
# Both the per-symbol Investor Lens card and the Scanner "lens" boards call these, so a stock's
# score is identical wherever it appears. Each returns 0-10, or None when inputs are too thin to
# judge (never fabricate). Boards apply their own stricter eligibility filters on top.


def graham_score(
    *,
    pe_ratio: float | None = None,
    pb_ratio: float | None = None,
    pe_vs_sector: float | None = None,
    roe: float | None = None,
    dividend_yield: float | None = None,
) -> int | None:
    if pe_vs_sector is None and pe_ratio is None and pb_ratio is None:
        return None
    score = 5.0
    if pe_vs_sector is not None:
        score += (
            2
            if pe_vs_sector < 0.75
            else 1
            if pe_vs_sector < 0.95
            else -2
            if pe_vs_sector > 1.25
            else 0
        )
    if pe_ratio is not None and pe_ratio > 0:
        score += 1 if pe_ratio <= 12 else -2 if pe_ratio > 25 else 0
    if pb_ratio is not None:
        score += 1 if pb_ratio < 1.2 else -1 if pb_ratio > 3 else 0
    if roe is not None and roe <= 0:
        score -= 2
    if dividend_yield is not None and dividend_yield >= 3:
        score += 1
    return _clamp10(score)


def buffett_quality_score(
    *,
    roe: float | None = None,
    eps_growth_yoy: float | None = None,
    dividend_yield: float | None = None,
    above_sma_200: bool | None = None,
) -> int | None:
    if roe is None and eps_growth_yoy is None:
        return None
    score = 5.0
    if roe is not None:
        score += 3 if roe >= 20 else 2 if roe >= 15 else 1 if roe >= 10 else -3 if roe <= 0 else -1
    if eps_growth_yoy is not None:
        score += (
            2
            if eps_growth_yoy >= 15
            else 1
            if eps_growth_yoy > 0
            else -2
            if eps_growth_yoy < -20
            else -1
        )
    if dividend_yield is not None and dividend_yield > 0:
        score += 1
    if above_sma_200 is False:
        score -= 1
    return _clamp10(score)


def technical_score(
    *,
    above_sma_50: bool | None = None,
    above_sma_200: bool | None = None,
    mom_12_1: float | None = None,
    rsi_14: float | None = None,
    relative_volume: float | None = None,
    pct_from_52w_high: float | None = None,
) -> int | None:
    if above_sma_50 is None and above_sma_200 is None and mom_12_1 is None and rsi_14 is None:
        return None
    score = 5.0
    score += 1.5 if above_sma_50 is True else -1 if above_sma_50 is False else 0
    score += 2 if above_sma_200 is True else -2 if above_sma_200 is False else 0
    if mom_12_1 is not None:
        score += 2 if mom_12_1 >= 40 else 1 if mom_12_1 > 0 else -1
    if rsi_14 is not None:
        score += 1 if 45 <= rsi_14 <= 70 else -1 if rsi_14 > 80 or rsi_14 < 30 else 0
    if relative_volume is not None and relative_volume >= 1.5:
        score += 1
    if pct_from_52w_high is not None and pct_from_52w_high > -2 and rsi_14 and rsi_14 > 75:
        score -= 1
    return _clamp10(score)


def smart_money_score(
    *,
    institute_delta: float | None = None,
    foreign_delta: float | None = None,
    cmf_20: float | None = None,
) -> int | None:
    if institute_delta is None and foreign_delta is None and cmf_20 is None:
        return None
    total = (institute_delta or 0) + (foreign_delta or 0)
    score = 5.0
    score += 3 if total >= 2 else 1 if total > 0 else -2 if total <= -2 else -1 if total < 0 else 0
    if (institute_delta or 0) > 0 and (foreign_delta or 0) > 0:
        score += 1
    if cmf_20 is not None:
        score += 1 if cmf_20 > 0.1 else -1 if cmf_20 < -0.1 else 0
    return _clamp10(score)


def risk_score(
    *,
    category: str | None = None,
    adtv_mn: float | None = None,
    free_float_cap_mn: float | None = None,
    volatility: float | None = None,
    today_change_pct: float | None = None,
) -> int | None:
    # Fragility needs at least a liquidity or volatility read; otherwise it's thin_data, not "safe".
    if adtv_mn is None and volatility is None:
        return None
    score = 8.0
    if category == "Z":
        score -= 3
    if adtv_mn is None:
        score -= 1
    elif adtv_mn < 2:
        score -= 3
    elif adtv_mn < 5:
        score -= 2
    elif adtv_mn < 10:
        score -= 1
    if free_float_cap_mn is not None and free_float_cap_mn < 100:
        score -= 1
    if volatility is not None:
        score -= 2 if volatility >= 80 else 1 if volatility >= 50 else 0
    if today_change_pct is not None and abs(today_change_pct) >= 9.7:
        score -= 2
    return _clamp10(score)


def dividend_score(
    *,
    dividend_yield: float | None = None,
    roe: float | None = None,
    eps_growth_yoy: float | None = None,
) -> int | None:
    """Cash-income read: yield rewarded, but only when earnings look able to sustain it. A very high
    yield with thin/negative earnings is docked as a possible dividend trap."""
    if dividend_yield is None:
        return None
    if dividend_yield <= 0:
        return 2  # pays no cash dividend — weak on the income lens (known, not thin data)
    score = 5.0
    score += (
        3 if dividend_yield >= 6 else 2 if dividend_yield >= 4 else 1 if dividend_yield >= 2 else 0
    )
    if roe is not None:
        score += 1 if roe >= 10 else -2 if roe <= 0 else 0
    if eps_growth_yoy is not None:
        score += 1 if eps_growth_yoy >= 0 else -1 if eps_growth_yoy < -20 else 0
    if dividend_yield >= 10 and (roe is None or roe < 5):
        score -= 1  # yield-trap guard
    return _clamp10(score)


def _verdict(score: int | None) -> str:
    if score is None:
        return "thin_data"
    return "supportive" if score >= 7 else "mixed" if score >= 4 else "caution"


def _fmt_pct(v: float | None, suffix: str = "%") -> str:
    return "—" if v is None else f"{v:.1f}{suffix}"


def _fmt_x(v: float | None) -> str:
    return "—" if v is None else f"{v:.1f}x"


def _fmt_tk_mn(v: float | None) -> str:
    if v is None:
        return "—"
    if v >= 10:
        return f"৳{v / 10:.1f}cr"
    return f"৳{v:.1f}mn"


def _fmt_tk(v: float | None) -> str:
    return "—" if v is None else f"৳{v:.1f}"


def _chk(label, val, want, *, good, weak, fmt=_fmt_x) -> LensCheck:
    """Build an actual-vs-expected check. `good`/`weak` are predicates on the value (only called when
    it's present), so the reader sees their number, the style's benchmark, and where it stands."""
    if val is None:
        return LensCheck(label=label, actual="—", expected=want, status="na")
    return LensCheck(
        label=label,
        actual=fmt(val),
        expected=want,
        status="pass" if good(val) else "fail" if weak(val) else "watch",
    )


def _news_check(bn: bool, count: int, label: str | None) -> LensCheck:
    """Recent material announcements (last 90d) — surfaced so the user doesn't have to go hunt."""
    if count > 0:
        base = f"{count}টি সাম্প্রতিক" if bn else f"{count} recent"
        actual = f"{base} · {label}" if label else base
        status = "watch"  # there's fresh news worth reading before acting
    else:
        actual = "নেই (৯০ দিনে)" if bn else "None (90d)"
        status = "na"  # absence of news is neutral, not a plus — don't paint it green
    return LensCheck(
        label="সাম্প্রতিক খবর" if bn else "Recent news", actual=actual, expected="", status=status
    )


def _extended_technical(
    *,
    pct_from_52w_high: float | None,
    rsi_14: float | None,
    mom_12_1: float | None,
) -> bool:
    near_high = pct_from_52w_high is not None and pct_from_52w_high >= -3
    hot_rsi = rsi_14 is not None and rsi_14 >= 72
    strong_run = mom_12_1 is not None and mom_12_1 >= 35
    return hot_rsi and (near_high or strong_run)


def _headline(lenses: list[InvestorLens], bn: bool) -> str:
    supportive = [lens.name for lens in lenses if lens.verdict == "supportive"]
    cautions = [lens.name for lens in lenses if lens.verdict == "caution"]
    if bn:
        if supportive and cautions:
            return f"সবচেয়ে সহায়ক: {supportive[0]} · সতর্কতা: {cautions[0]}"
        if supportive:
            return f"সবচেয়ে সহায়ক লেন্স: {supportive[0]}"
        if cautions:
            return f"প্রধান সতর্কতার লেন্স: {cautions[0]}"
        return "ডেটা মিশ্র — একাধিক লেন্স মিলিয়ে পড়ুন।"
    if supportive and cautions:
        return f"Best-supported: {supportive[0]} · Main caution: {cautions[0]}"
    if supportive:
        return f"Best-supported lens: {supportive[0]}"
    if cautions:
        return f"Main caution lens: {cautions[0]}"
    return "Mixed data — read across lenses, not from one score."


def _graham(
    *,
    bn: bool,
    pe_ratio: float | None,
    pb_ratio: float | None,
    pe_vs_sector: float | None,
    roe: float | None,
    dividend_yield: float | None,
    debt_to_equity: float | None = None,
    recent_news_count: int = 0,
    recent_news_label: str | None = None,
) -> InvestorLens:
    s = graham_score(
        pe_ratio=pe_ratio,
        pb_ratio=pb_ratio,
        pe_vs_sector=pe_vs_sector,
        roe=roe,
        dividend_yield=dividend_yield,
    )
    if bn:
        summary = "খাতের তুলনায় দাম কতটা যুক্তিযুক্ত এবং আয়ের সাপোর্ট আছে কি না — এই লেন্স তা দেখে।"
        points = [
            f"P/E vs sector: {_fmt_x(pe_vs_sector)}",
            f"P/E {_fmt_x(pe_ratio)} · P/B {_fmt_x(pb_ratio)}",
            f"ROE {_fmt_pct(roe)} · dividend yield {_fmt_pct(dividend_yield)}",
        ]
        watch_next = []
    else:
        summary = "Checks whether valuation is reasonable versus sector peers and backed by earnings quality."
        points = [
            f"P/E vs sector: {_fmt_x(pe_vs_sector)}",
            f"P/E {_fmt_x(pe_ratio)} · P/B {_fmt_x(pb_ratio)}",
            f"ROE {_fmt_pct(roe)} · dividend yield {_fmt_pct(dividend_yield)}",
        ]
        watch_next = []

    checks = [
        _chk(
            "খাতের চেয়ে সস্তা" if bn else "Cheaper than sector",
            pe_vs_sector,
            "< 1.0x",
            good=lambda x: x < 0.9,
            weak=lambda x: x > 1.25,
        ),
        _chk("P/E", pe_ratio, "≤ 15x", good=lambda x: 0 < x <= 15, weak=lambda x: x > 25),
        _chk("P/B", pb_ratio, "≤ 1.5x", good=lambda x: x <= 1.5, weak=lambda x: x > 3),
        _chk(
            "আয় (ROE)" if bn else "Earnings (ROE)",
            roe,
            "≥ 10%",
            good=lambda x: x >= 10,
            weak=lambda x: x <= 0,
            fmt=_fmt_pct,
        ),
        _chk(
            "লভ্যাংশ" if bn else "Dividend",
            dividend_yield,
            "≥ 3%",
            good=lambda x: x >= 3,
            weak=lambda x: x <= 0,
            fmt=_fmt_pct,
        ),
        _chk(
            "ঋণ/ইকুইটি" if bn else "Debt / equity",
            debt_to_equity,
            "≤ 1.0x",
            good=lambda x: x <= 0.5,
            weak=lambda x: x > 2,
            fmt=_fmt_x,
        ),
        _news_check(bn, recent_news_count, recent_news_label),
    ]
    return InvestorLens(
        key="graham_value",
        name="Graham Value",
        persona="Margin-of-safety value read",
        verdict=_verdict(s),
        score=s,
        summary=summary,
        points=points,
        checks=checks,
        watch_next=watch_next,
    )


def _buffett(
    *,
    bn: bool,
    roe: float | None,
    eps_growth_yoy: float | None,
    dividend_yield: float | None,
    above_sma_200: bool | None,
    debt_to_equity: float | None = None,
    credit_rating: str | None = None,
    eps_history: list[float] | None = None,
) -> InvestorLens:
    s = buffett_quality_score(
        roe=roe,
        eps_growth_yoy=eps_growth_yoy,
        dividend_yield=dividend_yield,
        above_sma_200=above_sma_200,
    )
    # Multi-year EPS trend from annual financials (oldest -> newest): how many years earnings rose.
    eps_years_up: int | None = None
    eps_years_n = 0
    if eps_history and len(eps_history) >= 2:
        pairs = list(pairwise(eps_history))
        eps_years_up = sum(1 for a, b in pairs if b >= a)
        eps_years_n = len(pairs)
    if bn:
        summary = "ব্যবসার মান, লাভজনকতা ও স্থায়িত্বের দিক থেকে কোম্পানিটা কতটা শক্ত — এই লেন্স তা দেখে।"
        trend = (
            "200DMA-এর উপরে"
            if above_sma_200
            else "200DMA-এর নিচে"
            if above_sma_200 is False
            else "দীর্ঘমেয়াদি ট্রেন্ড অজানা"
        )
        points = [f"ROE {_fmt_pct(roe)}", f"EPS growth {_fmt_pct(eps_growth_yoy)}", trend]
        watch_next = ["ব্যবসার moat"]
    else:
        summary = (
            "Looks for business quality: durable profitability, steady earnings, and staying power."
        )
        trend = (
            "Above 200-DMA"
            if above_sma_200
            else "Below 200-DMA"
            if above_sma_200 is False
            else "Long-term trend unknown"
        )
        points = [f"ROE {_fmt_pct(roe)}", f"EPS growth {_fmt_pct(eps_growth_yoy)}", trend]
        watch_next = ["Business moat"]

    checks = [
        _chk(
            "লাভজনকতা (ROE)" if bn else "Profitability (ROE)",
            roe,
            "≥ 15%",
            good=lambda x: x >= 15,
            weak=lambda x: x <= 0,
            fmt=_fmt_pct,
        ),
        _chk(
            "আয় বৃদ্ধি (YoY)" if bn else "Earnings growth (YoY)",
            eps_growth_yoy,
            "> 0%",
            good=lambda x: x >= 15,
            weak=lambda x: x < 0,
            fmt=_fmt_pct,
        ),
        _chk(
            "ঋণ/ইকুইটি" if bn else "Debt / equity",
            debt_to_equity,
            "≤ 1.0x",
            good=lambda x: x <= 0.5,
            weak=lambda x: x > 2,
            fmt=_fmt_x,
        ),
        LensCheck(
            label="বহু-বছরের আয়" if bn else "Multi-year earnings",
            actual=(
                f"{eps_years_up}/{eps_years_n} বছর বেড়েছে"
                if bn
                else f"up {eps_years_up}/{eps_years_n} yrs"
            )
            if eps_years_up is not None
            else "—",
            expected="ধারাবাহিক" if bn else "rising",
            status=(
                "na"
                if eps_years_up is None
                else "pass"
                if eps_years_up >= eps_years_n * 0.6
                else "fail"
                if eps_years_up == 0
                else "watch"
            ),
        ),
        LensCheck(
            label="ক্রেডিট রেটিং" if bn else "Credit rating",
            actual=credit_rating or "—",
            expected="investment grade" if not bn else "ইনভেস্টমেন্ট গ্রেড",
            status="na"
            if not credit_rating
            else (
                "pass" if credit_rating.strip().upper().startswith(("AAA", "AA", "A")) else "watch"
            ),
        ),
        LensCheck(
            label="দীর্ঘমেয়াদি ট্রেন্ড" if bn else "Long-term trend",
            actual=("200DMA উপরে" if bn else "Above 200-DMA")
            if above_sma_200
            else ("200DMA নিচে" if bn else "Below 200-DMA")
            if above_sma_200 is False
            else "—",
            expected="↑ 200-DMA",
            status="pass" if above_sma_200 else "fail" if above_sma_200 is False else "na",
        ),
    ]
    return InvestorLens(
        key="buffett_quality",
        name="Buffett/Munger Quality",
        persona="Quality business read",
        verdict=_verdict(s),
        score=s,
        summary=summary,
        points=points,
        checks=checks,
        watch_next=watch_next,
    )


def _technical(
    *,
    bn: bool,
    above_sma_50: bool | None,
    above_sma_200: bool | None,
    mom_12_1: float | None,
    rsi_14: float | None,
    relative_volume: float | None,
    pct_from_52w_high: float | None,
    nearest_support: float | None = None,
    nearest_resistance: float | None = None,
    last_close: float | None = None,
) -> InvestorLens:
    if above_sma_50 is None and above_sma_200 is None and mom_12_1 is None and rsi_14 is None:
        s = None
    else:
        score = 5.0
        score += 1.5 if above_sma_50 is True else -1 if above_sma_50 is False else 0
        score += 2 if above_sma_200 is True else -2 if above_sma_200 is False else 0
        if mom_12_1 is not None:
            score += 2 if mom_12_1 >= 40 else 1 if mom_12_1 > 0 else -1
        if rsi_14 is not None:
            score += 1 if 45 <= rsi_14 <= 70 else -1 if rsi_14 > 80 or rsi_14 < 30 else 0
        if relative_volume is not None and relative_volume >= 1.5:
            score += 1
        if pct_from_52w_high is not None and pct_from_52w_high > -2 and rsi_14 and rsi_14 > 75:
            score -= 1
        extended = _extended_technical(
            pct_from_52w_high=pct_from_52w_high,
            rsi_14=rsi_14,
            mom_12_1=mom_12_1,
        )
        if extended:
            score = min(score, 6.0)
        s = _clamp10(score)
    extended = _extended_technical(
        pct_from_52w_high=pct_from_52w_high,
        rsi_14=rsi_14,
        mom_12_1=mom_12_1,
    )

    if bn:
        summary = (
            "চার্ট শক্ত, তবে দাম অনেকটা দৌড়ে ৫২-সপ্তাহের উচ্চতার কাছে এবং RSI গরম — chase না করে pullback/support দেখুন।"
            if extended
            else "চার্ট, ট্রেন্ড, ভলিউম ও RSI দিয়ে ট্রেডাররা এখনকার অবস্থান কীভাবে পড়বে — এই লেন্স তা দেখায়।"
        )
        trend = (
            f"50DMA {'উপরে' if above_sma_50 else 'নিচে' if above_sma_50 is False else 'অজানা'} · "
            f"200DMA {'উপরে' if above_sma_200 else 'নিচে' if above_sma_200 is False else 'অজানা'}"
        )
        points = [
            trend,
            f"12m momentum {_fmt_pct(mom_12_1)} · RSI {_fmt_pct(rsi_14, '')}",
            f"Volume {_fmt_x(relative_volume)} normal",
        ]
        watch_next = ["pullback/support", "RSI ঠান্ডা হয় কি না"] if extended else []
    else:
        summary = (
            "Trend is strong, but price is extended near its 52-week high with hot RSI. Treat this as chase-risk; wait for pullback/support confirmation."
            if extended
            else "Reads the chart setup: trend, momentum, volume confirmation, and short-term stretch."
        )
        trend = (
            f"50-DMA {'above' if above_sma_50 else 'below' if above_sma_50 is False else 'unknown'} · "
            f"200-DMA {'above' if above_sma_200 else 'below' if above_sma_200 is False else 'unknown'}"
        )
        points = [
            trend,
            f"12m momentum {_fmt_pct(mom_12_1)} · RSI {_fmt_pct(rsi_14, '')}",
            f"Volume {_fmt_x(relative_volume)} normal",
        ]
        watch_next = ["Pullback/support", "RSI cools"] if extended else []

    checks = [
        LensCheck(
            label="50-দিনের ট্রেন্ড" if bn else "50-day trend",
            actual=("উপরে" if bn else "Above")
            if above_sma_50
            else ("নিচে" if bn else "Below")
            if above_sma_50 is False
            else "—",
            expected="↑ 50-DMA",
            status="pass" if above_sma_50 else "fail" if above_sma_50 is False else "na",
        ),
        LensCheck(
            label="200-দিনের ট্রেন্ড" if bn else "200-day trend",
            actual=("উপরে" if bn else "Above")
            if above_sma_200
            else ("নিচে" if bn else "Below")
            if above_sma_200 is False
            else "—",
            expected="↑ 200-DMA",
            status="pass" if above_sma_200 else "fail" if above_sma_200 is False else "na",
        ),
        _chk(
            "মোমেন্টাম (12m)" if bn else "Momentum (12m)",
            mom_12_1,
            "> 0%",
            good=lambda x: x >= 40,
            weak=lambda x: x <= 0,
            fmt=_fmt_pct,
        ),
        _chk(
            "RSI",
            rsi_14,
            "45-70",
            good=lambda x: 45 <= x <= 70,
            weak=lambda x: x > 80 or x < 30,
            fmt=lambda v: _fmt_pct(v, ""),
        ),
        _chk(
            "ভলিউম (স্বাভাবিকের বিপরীতে)" if bn else "Volume vs normal",
            relative_volume,
            "≥ 1.5x" + (" নিশ্চিতকরণে" if bn else " to confirm"),
            good=lambda x: x >= 1.5,
            weak=lambda x: x < 0.7,
            fmt=_fmt_x,
        ),
        LensCheck(
            label="সাপোর্ট / রেজিস্ট্যান্স" if bn else "Support / resistance",
            actual=f"{_fmt_tk(nearest_support)} / {_fmt_tk(nearest_resistance)}"
            if (nearest_support is not None or nearest_resistance is not None)
            else "—",
            expected="",
            status="na",
        ),
    ]
    return InvestorLens(
        key="technical_trader",
        name="Technical Trader",
        persona="Price-action read",
        verdict=_verdict(s),
        score=s,
        summary=summary,
        points=points,
        checks=checks,
        watch_next=watch_next,
    )


def _smart_money(
    *,
    bn: bool,
    institute_delta: float | None,
    foreign_delta: float | None,
    institute_pct: float | None,
    foreign_pct: float | None,
    cmf_20: float | None,
    recent_news_count: int = 0,
    recent_news_label: str | None = None,
    next_meeting_date: str | None = None,
    next_meeting_period: str | None = None,
) -> InvestorLens:
    s = smart_money_score(
        institute_delta=institute_delta, foreign_delta=foreign_delta, cmf_20=cmf_20
    )
    if bn:
        summary = "প্রতিষ্ঠান/বিদেশি মালিকানা ও মানি-ফ্লো দেখে বড় অংশগ্রহণকারীদের আচরণ বোঝার চেষ্টা করে।"
        points = [
            f"Institutions {_fmt_pct(institute_pct)} ({_fmt_pct(institute_delta, ' pp')})",
            f"Foreign {_fmt_pct(foreign_pct)} ({_fmt_pct(foreign_delta, ' pp')})",
            f"Chaikin money flow {_fmt_pct(cmf_20, '')}",
        ]
        watch_next = []
    else:
        summary = "Checks whether institutional/foreign ownership and money flow support the story."
        points = [
            f"Institutions {_fmt_pct(institute_pct)} ({_fmt_pct(institute_delta, ' pp')})",
            f"Foreign {_fmt_pct(foreign_pct)} ({_fmt_pct(foreign_delta, ' pp')})",
            f"Chaikin money flow {_fmt_pct(cmf_20, '')}",
        ]
        watch_next = []

    checks = [
        _chk(
            "প্রতিষ্ঠান বদল" if bn else "Institutions change",
            institute_delta,
            "> 0 pp",
            good=lambda x: x > 0,
            weak=lambda x: x < 0,
            fmt=lambda v: _fmt_pct(v, " pp"),
        ),
        _chk(
            "বিদেশি বদল" if bn else "Foreign change",
            foreign_delta,
            "> 0 pp",
            good=lambda x: x > 0,
            weak=lambda x: x < 0,
            fmt=lambda v: _fmt_pct(v, " pp"),
        ),
        _chk(
            "মানি ফ্লো (CMF)" if bn else "Money flow (CMF)",
            cmf_20,
            "> 0",
            good=lambda x: x > 0.1,
            weak=lambda x: x < -0.1,
            fmt=lambda v: _fmt_pct(v, ""),
        ),
        _news_check(bn, recent_news_count, recent_news_label),
        LensCheck(
            label="পরবর্তী বোর্ড সভা" if bn else "Next board meeting",
            actual=(
                f"{next_meeting_date} ({next_meeting_period})"
                if next_meeting_period
                else next_meeting_date
            )
            if next_meeting_date
            else ("নির্ধারিত নেই" if bn else "none scheduled"),
            expected="",
            status="watch" if next_meeting_date else "na",
        ),
    ]
    return InvestorLens(
        key="smart_money",
        name="Smart Money",
        persona="Ownership-flow read",
        verdict=_verdict(s),
        score=s,
        summary=summary,
        points=points,
        checks=checks,
        watch_next=watch_next,
    )


def _dividend(
    *,
    bn: bool,
    dividend_yield: float | None,
    roe: float | None,
    eps_growth_yoy: float | None,
    div_paid_years: int = 0,
    div_total_years: int = 0,
    latest_cash_pct: float | None = None,
    latest_bonus_pct: float | None = None,
) -> InvestorLens:
    s = dividend_score(dividend_yield=dividend_yield, roe=roe, eps_growth_yoy=eps_growth_yoy)
    no_div = (dividend_yield or 0) <= 0
    if bn:
        summary = "নগদ লভ্যাংশের ইয়িল্ড এবং আয় দিয়ে তা টেকসই কি না — এই লেন্স তা দেখে।"
        points = [
            f"Dividend yield {_fmt_pct(dividend_yield)}",
            f"ROE {_fmt_pct(roe)} · EPS growth {_fmt_pct(eps_growth_yoy)}",
            "নগদ লভ্যাংশ নেই" if no_div else "আয় লভ্যাংশ কভার করছে কি না দেখুন",
        ]
        watch_next = ["রেকর্ড ডেট"]
    else:
        summary = "Checks cash-dividend yield and whether earnings can sustain it."
        points = [
            f"Dividend yield {_fmt_pct(dividend_yield)}",
            f"ROE {_fmt_pct(roe)} · EPS growth {_fmt_pct(eps_growth_yoy)}",
            "No cash dividend" if no_div else "Verify earnings cover the payout",
        ]
        watch_next = ["Record date"]
    checks = [
        _chk(
            "নগদ ইয়িল্ড" if bn else "Cash yield",
            dividend_yield,
            "≥ 4%",
            good=lambda x: x >= 4,
            weak=lambda x: x <= 0,
            fmt=_fmt_pct,
        ),
        _chk(
            "আয় কভারেজ (ROE)" if bn else "Earnings cover (ROE)",
            roe,
            "≥ 10%",
            good=lambda x: x >= 10,
            weak=lambda x: x <= 0,
            fmt=_fmt_pct,
        ),
        _chk(
            "আয় স্থিতিশীল" if bn else "Earnings stable",
            eps_growth_yoy,
            "≥ 0%",
            good=lambda x: x >= 0,
            weak=lambda x: x < -20,
            fmt=_fmt_pct,
        ),
        LensCheck(
            label="লভ্যাংশ ট্র্যাক রেকর্ড" if bn else "Payout track record",
            actual=(
                f"নগদ {div_paid_years}/{div_total_years} বছর"
                if bn
                else f"cash {div_paid_years}/{div_total_years} yrs"
            )
            if div_total_years
            else "—",
            expected="≥ 3 yrs" if div_total_years else "",
            status=(
                "na"
                if not div_total_years
                else "pass"
                if div_paid_years >= 3
                else "watch"
                if div_paid_years >= 1
                else "fail"
            ),
        ),
        LensCheck(
            label="সর্বশেষ পেআউট" if bn else "Latest payout",
            actual=(
                (f"নগদ {latest_cash_pct:.0f}%" if bn else f"cash {latest_cash_pct:.0f}%")
                + (
                    (
                        f" + বোনাস {latest_bonus_pct:.0f}%"
                        if bn
                        else f" + bonus {latest_bonus_pct:.0f}%"
                    )
                    if latest_bonus_pct
                    else ""
                )
            )
            if latest_cash_pct is not None
            else "—",
            expected="",
            status="na",
        ),
    ]
    return InvestorLens(
        key="dividend_income",
        name="Dividend Investor",
        persona="Cash-income read",
        verdict=_verdict(s),
        score=s,
        summary=summary,
        points=points,
        checks=checks,
        watch_next=watch_next,
    )


def _taleb_risk(
    *,
    bn: bool,
    category: str | None,
    adtv_mn: float | None,
    free_float_cap_mn: float | None,
    volatility: float | None,
    today_change_pct: float | None,
) -> InvestorLens:
    s = risk_score(
        category=category,
        adtv_mn=adtv_mn,
        free_float_cap_mn=free_float_cap_mn,
        volatility=volatility,
        today_change_pct=today_change_pct,
    )
    order_guide = adtv_mn * 0.05 if adtv_mn is not None else None

    if bn:
        summary = "ভুল হলে বের হওয়া কতটা কঠিন হতে পারে — লিকুইডিটি, ভোলাটিলিটি ও ক্যাটাগরি দিয়ে তা পড়ে।"
        points = [
            f"Category {category or '—'}",
            f"ADTV {_fmt_tk_mn(adtv_mn)} · rough 5% order guide {_fmt_tk_mn(order_guide)}",
            f"Volatility {_fmt_pct(volatility)} · today {_fmt_pct(today_change_pct)}",
        ]
        watch_next = ["বিড-আস্ক স্প্রেড", "অর্ডার সাইজ", "নিজের stop-loss"]
    else:
        summary = "Focuses on fragility: exit risk, volatility, category risk, and whether orders can move price."
        points = [
            f"Category {category or '—'}",
            f"ADTV {_fmt_tk_mn(adtv_mn)} · rough 5% order guide {_fmt_tk_mn(order_guide)}",
            f"Volatility {_fmt_pct(volatility)} · today {_fmt_pct(today_change_pct)}",
        ]
        watch_next = ["Bid-ask spread", "Order size", "Your stop-loss"]

    checks = [
        LensCheck(
            label="ক্যাটাগরি" if bn else "Category",
            actual=category or "—",
            expected="A / B",
            status="fail" if category == "Z" else "pass" if category else "na",
        ),
        _chk(
            "লিকুইডিটি (ADTV)" if bn else "Liquidity (ADTV)",
            adtv_mn,
            "≥ ৳5mn/day",
            good=lambda x: x >= 10,
            weak=lambda x: x < 5,
            fmt=_fmt_tk_mn,
        ),
        _chk(
            "ভোলাটিলিটি" if bn else "Volatility",
            volatility,
            "< 50%",
            good=lambda x: x < 35,
            weak=lambda x: x >= 50,
            fmt=_fmt_pct,
        ),
        _chk(
            "আজকের মুভ" if bn else "Today's move",
            today_change_pct,
            "সার্কিটে নয়" if bn else "not at circuit",
            good=lambda x: abs(x) < 7,
            weak=lambda x: abs(x) >= 9.5,
            fmt=_fmt_pct,
        ),
    ]
    return InvestorLens(
        key="taleb_risk",
        name="Taleb Risk",
        persona="Downside and exit-risk read",
        verdict=_verdict(s),
        score=s,
        summary=summary,
        points=points,
        checks=checks,
        watch_next=watch_next,
    )


def build_investor_lens(
    *,
    code: str,
    as_of_date: str,
    locale: str = "en",
    category: str | None = None,
    pe_ratio: float | None = None,
    pb_ratio: float | None = None,
    pe_vs_sector: float | None = None,
    roe: float | None = None,
    eps_growth_yoy: float | None = None,
    dividend_yield: float | None = None,
    above_sma_50: bool | None = None,
    above_sma_200: bool | None = None,
    mom_12_1: float | None = None,
    rsi_14: float | None = None,
    relative_volume: float | None = None,
    pct_from_52w_high: float | None = None,
    institute_pct: float | None = None,
    foreign_pct: float | None = None,
    institute_delta: float | None = None,
    foreign_delta: float | None = None,
    cmf_20: float | None = None,
    adtv_mn: float | None = None,
    free_float_cap_mn: float | None = None,
    volatility: float | None = None,
    today_change_pct: float | None = None,
    debt_to_equity: float | None = None,
    credit_rating: str | None = None,
    nearest_support: float | None = None,
    nearest_resistance: float | None = None,
    last_close: float | None = None,
    recent_news_count: int = 0,
    recent_news_label: str | None = None,
    div_paid_years: int = 0,
    div_total_years: int = 0,
    latest_cash_pct: float | None = None,
    latest_bonus_pct: float | None = None,
    eps_history: list[float] | None = None,
    next_meeting_date: str | None = None,
    next_meeting_period: str | None = None,
) -> InvestorLensResponse:
    """Build the six best-fit DSE lenses for a symbol."""
    bn = locale == "bn"
    lenses = [
        _graham(
            bn=bn,
            pe_ratio=pe_ratio,
            pb_ratio=pb_ratio,
            pe_vs_sector=pe_vs_sector,
            roe=roe,
            dividend_yield=dividend_yield,
            debt_to_equity=debt_to_equity,
            recent_news_count=recent_news_count,
            recent_news_label=recent_news_label,
        ),
        _buffett(
            bn=bn,
            roe=roe,
            eps_growth_yoy=eps_growth_yoy,
            dividend_yield=dividend_yield,
            above_sma_200=above_sma_200,
            debt_to_equity=debt_to_equity,
            credit_rating=credit_rating,
            eps_history=eps_history,
        ),
        _dividend(
            bn=bn,
            dividend_yield=dividend_yield,
            roe=roe,
            eps_growth_yoy=eps_growth_yoy,
            div_paid_years=div_paid_years,
            div_total_years=div_total_years,
            latest_cash_pct=latest_cash_pct,
            latest_bonus_pct=latest_bonus_pct,
        ),
        _technical(
            bn=bn,
            above_sma_50=above_sma_50,
            above_sma_200=above_sma_200,
            mom_12_1=mom_12_1,
            rsi_14=rsi_14,
            relative_volume=relative_volume,
            pct_from_52w_high=pct_from_52w_high,
            nearest_support=nearest_support,
            nearest_resistance=nearest_resistance,
            last_close=last_close,
        ),
        _smart_money(
            bn=bn,
            institute_delta=institute_delta,
            foreign_delta=foreign_delta,
            institute_pct=institute_pct,
            foreign_pct=foreign_pct,
            cmf_20=cmf_20,
            recent_news_count=recent_news_count,
            recent_news_label=recent_news_label,
            next_meeting_date=next_meeting_date,
            next_meeting_period=next_meeting_period,
        ),
        _taleb_risk(
            bn=bn,
            category=category,
            adtv_mn=adtv_mn,
            free_float_cap_mn=free_float_cap_mn,
            volatility=volatility,
            today_change_pct=today_change_pct,
        ),
    ]
    return InvestorLensResponse(
        code=code,
        as_of_date=as_of_date,
        headline=_headline(lenses, bn),
        lenses=lenses,
        disclaimer=_DISCLAIMER["bn" if bn else "en"],
    )
