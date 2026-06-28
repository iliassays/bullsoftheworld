"""Factor agents — descriptive notes from the institutional-grade analytics (momentum, quality,
relative strength, broad smart-money accumulation).

Pure detection over a precomputed TickerAnalytics row (+ today's price vs the index for strength).
Event-gated via occurrence keys + the runner's cooldown so a name posts at most ~once a month per
factor. Strictly descriptive — facts about a factor, never buy/sell. No LLM.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FactorSignal:
    beat: str  # agent beat key (momentum | quality | smartmoney | strength)
    event_type: str
    occurrence_key: str
    cooldown_days: int
    payload: dict


# --- thresholds (calibrated to the DSE factor distributions) ---
_MOM_MIN = 60.0  # 12-1 month return % to count as a "strong trend"
_MOM_PUMP = 300.0  # above this (or high + tiny cap) it's a likely pump, flag caution
_PUMP_MCAP_MN = 1000.0
_QUALITY_PE_VS = 0.8  # cheaper than 0.8x the sector median
_QUALITY_ROE = 15.0  # strong return on equity
_SMART_MIN_PP = 2.0  # combined institutional + foreign stake rise (pp)
_STRENGTH_UP = 2.0  # stock up at least this % ...
_STRENGTH_IDX = -0.3  # ... while DSEX fell at least this much
_ACCUM_CMF = 0.10  # quiet accumulation: money inflow (Chaikin) ...
_ACCUM_BAND = 0.10  # ... while price stays within ±10% of its 50-day base
_CIRCUIT = 9.7  # DSE daily ±10% limit — locked stocks settle ~9.7-9.95 (tick rounding under 10%)
_BREAKOUT_NEAR = -2.0  # within 2% of the 52-week high ...
_BREAKOUT_UP = 1.0  # ... and up at least this much today (a fresh push, not just sitting there)


def detect_momentum(ta, month_key: str) -> FactorSignal | None:
    if ta.mom_12_1 is None or not ta.volatility or ta.mom_12_1 < _MOM_MIN:
        return None
    pump = ta.mom_12_1 >= _MOM_PUMP or (
        ta.mom_12_1 >= 150 and (ta.market_cap_mn or 0) < _PUMP_MCAP_MN
    )
    return FactorSignal(
        "momentum",
        "momentum_strong",
        f"momentum:{month_key}",
        20,
        {"mom": round(ta.mom_12_1), "pump": pump},
    )


def detect_quality(ta, month_key: str) -> FactorSignal | None:
    if ta.pe_vs_sector is None or ta.roe is None or not ta.pe_ratio or ta.pe_ratio <= 0:
        return None
    if ta.pe_vs_sector < _QUALITY_PE_VS and ta.roe >= _QUALITY_ROE:
        return FactorSignal(
            "quality",
            "quality_value",
            f"quality:{month_key}",
            20,
            {"pe_vs": round(ta.pe_vs_sector, 2), "roe": round(ta.roe)},
        )
    return None


def detect_smartmoney(ta, month_key: str) -> FactorSignal | None:
    id_, fd = ta.institute_delta, ta.foreign_delta
    if id_ is None or fd is None or id_ <= 0 or fd <= 0 or (id_ + fd) < _SMART_MIN_PP:
        return None
    return FactorSignal(
        "smartmoney", "smart_money_both", f"smartmoney:{month_key}", 20, {"pp": round(id_ + fd, 1)}
    )


def detect_accumulation(ta, month_key: str) -> FactorSignal | None:
    """Money flowing in (Chaikin) AND volume confirming (OBV up) while price stays in its base —
    the quiet-accumulation divergence. Mirrors the `quiet_accumulation` screen."""
    cmf, obv, sma, px = ta.cmf_20, ta.obv_slope, ta.sma_50, ta.last_close
    if cmf is None or obv is None or sma is None or px is None or sma <= 0:
        return None
    if cmf >= _ACCUM_CMF and obv > 0 and (1 - _ACCUM_BAND) <= px / sma <= (1 + _ACCUM_BAND):
        return FactorSignal(
            "accumulation",
            "quiet_accumulation",
            f"accumulation:{month_key}",
            20,
            {"cmf": round(cmf, 2)},
        )
    return None


def detect_circuit(change_pct: float | None, day: str) -> FactorSignal | None:
    """Hit the DSE daily price limit — locked up (+~10%) or down (-~10%). Once per name per day."""
    if change_pct is None:
        return None
    if change_pct >= _CIRCUIT:
        return FactorSignal("circuit", "circuit_up", f"circuit:{day}", 1, {"dir": "up", "chg": round(change_pct, 1)})
    if change_pct <= -_CIRCUIT:
        return FactorSignal("circuit", "circuit_down", f"circuit:{day}", 1, {"dir": "down", "chg": round(change_pct, 1)})
    return None


def detect_breakout(ta, change_pct: float | None, day: str) -> FactorSignal | None:
    """Pushing to a new 52-week high: within 2% of the high AND up meaningfully today."""
    pfh = getattr(ta, "pct_from_52w_high", None)
    if pfh is None or change_pct is None:
        return None
    if pfh >= _BREAKOUT_NEAR and change_pct >= _BREAKOUT_UP:
        return FactorSignal("breakout", "new_52w_high", f"breakout:{day}", 7, {})
    return None


def detect_strength(
    change_pct: float | None, dsex_change: float | None, day: str
) -> FactorSignal | None:
    if change_pct is None or dsex_change is None:
        return None
    if change_pct >= _STRENGTH_UP and dsex_change <= _STRENGTH_IDX:
        return FactorSignal(
            "strength",
            "rel_strength",
            f"strength:{day}",
            3,
            {"chg": round(change_pct, 1), "idx": round(dsex_change, 1)},
        )
    return None


_T = {
    "momentum": (
        "{code} is among the market's strongest 12-month trends (about +{mom}% over the year).{pump} "
        "A fact about momentum — not advice.",
        "{code} বাজারের সবচেয়ে শক্তিশালী ১২-মাসের প্রবণতাগুলোর একটি (বছরে প্রায় +{mom}%)।{pump} "
        "এটি গতির একটি তথ্য — পরামর্শ নয়।",
    ),
    "quality": (
        "{code} trades below its sector's P/E ({pe_vs}x) with strong return on equity (~{roe}%) — "
        "quality at a discount. 'Cheap' can also mean the market sees a problem, so check why. Not advice.",
        "{code} তার খাতের গড় P/E-র নিচে ({pe_vs}x) লেনদেন হচ্ছে এবং ROE শক্তিশালী (~{roe}%) — "
        "সস্তায় মান। 'সস্তা' বাজারের কোনো সমস্যাও বোঝাতে পারে, তাই কারণ যাচাই করুন। পরামর্শ নয়।",
    ),
    "smartmoney": (
        "Both institutions and foreign investors raised their stake in {code} (+{pp} pp combined) at "
        "the latest disclosure — broad 'smart money' accumulation. History, not a forecast.",
        "সর্বশেষ প্রকাশে প্রতিষ্ঠান ও বিদেশি উভয় বিনিয়োগকারী {code}-এ অংশ বাড়িয়েছে (সম্মিলিত +{pp} pp) — "
        "বিস্তৃত 'স্মার্ট মানি' সঞ্চয়। ইতিহাস, পূর্বাভাস নয়।",
    ),
    "strength": (
        "{code} rose {chg}% while the market (DSEX) fell {idx_abs}% — relative strength. "
        "Descriptive, not advice.",
        "{code} {chg}% বেড়েছে যেখানে বাজার (DSEX) {idx_abs}% পড়েছে — আপেক্ষিক শক্তি। তথ্য, পরামর্শ নয়।",
    ),
    "accumulation": (
        "{code} is drawing steady money inflow while its price stays flat in its base — a quiet "
        "accumulation pattern (money in, price not yet moved). A divergence, not a promise. Not advice.",
        "{code}-তে ধারাবাহিক অর্থপ্রবাহ আসছে অথচ দাম এখনও তার ভিত্তিতে স্থির — একটি নীরব সঞ্চয়ের প্যাটার্ন "
        "(অর্থ ঢুকছে, দাম এখনও বাড়েনি)। এটি একটি ডাইভারজেন্স, নিশ্চয়তা নয়। পরামর্শ নয়।",
    ),
    "circuit_up": (
        "{code} hit today's upper price limit (+{chg}%) — buyers locked it at the ceiling. A strong "
        "demand signal, but limit moves can reverse. Descriptive, not advice.",
        "{code} আজ দিনের সর্বোচ্চ দামসীমা ছুঁয়েছে (+{chg}%) — ক্রেতারা সিলিংয়ে আটকে দিয়েছে। শক্তিশালী "
        "চাহিদার ইঙ্গিত, তবে সীমা-ছোঁয়া দাম উল্টেও যেতে পারে। তথ্যমূলক, পরামর্শ নয়।",
    ),
    "circuit_down": (
        "{code} hit today's lower price limit ({chg}%) — sellers pinned it at the floor. Descriptive, "
        "not advice.",
        "{code} আজ দিনের সর্বনিম্ন দামসীমা ছুঁয়েছে ({chg}%) — বিক্রেতারা মেঝেতে আটকে দিয়েছে। তথ্যমূলক, "
        "পরামর্শ নয়।",
    ),
    "breakout": (
        "{code} is pushing to a new 52-week high. Strength — but extended moves can pull back, so "
        "check the volume behind it. Descriptive, not advice.",
        "{code} নতুন ৫২-সপ্তাহের সর্বোচ্চে উঠছে। শক্তি — তবে বেশি বেড়ে গেলে পিছিয়ে আসতে পারে, তাই পেছনের "
        "ভলিউম দেখুন। তথ্যমূলক, পরামর্শ নয়।",
    ),
}


def render(sig: FactorSignal, code: str, locale: str) -> str:
    # circuit shares one beat but two templates (up/down), chosen by direction.
    key = ("circuit_up" if sig.payload.get("dir") == "up" else "circuit_down") if sig.beat == "circuit" else sig.beat
    tmpl = _T[key][1 if locale == "bn" else 0]
    p = dict(sig.payload, code=code)
    if sig.beat == "momentum":
        caution = (
            " A move this fast can reverse hard — treat with care."
            if locale != "bn"
            else " এত দ্রুত মুভমেন্ট দ্রুত উল্টে যেতে পারে — সতর্ক থাকুন।"
        )
        p["pump"] = caution if p.get("pump") else ""
    if sig.beat == "strength":
        p["idx_abs"] = abs(p["idx"])
    return tmpl.format(**p)
