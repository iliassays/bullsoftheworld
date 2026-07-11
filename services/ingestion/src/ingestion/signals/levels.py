"""Levels-agent: detect EOD price-structure events by comparing today vs yesterday.

Pure + I/O-free. `detect` takes two AnalyticsResult snapshots (today, and as-of-yesterday computed
from bars[:-1]) and returns the events that just became true. `render` turns an event into a
bilingual, descriptive note — a fact plus a plain "what it means," never advice.
"""

from __future__ import annotations

from dataclasses import dataclass

from bulls.analytics.engine import AnalyticsResult

BEAT = "levels"
_BREAKOUT_RELVOL = 1.2  # a breakout is "confirmed" only on at-least-average volume


@dataclass
class Signal:
    event_type: str
    occurrence_key: str  # unique per instance (the date it became true)
    payload: dict


def detect(prev: AnalyticsResult | None, today: AnalyticsResult) -> list[Signal]:
    if prev is None:
        return []
    out: list[Signal] = []
    key = str(today.as_of_date)
    close = today.last_close
    relvol = today.relative_volume or 0.0

    if prev.week52_high and close > prev.week52_high:
        out.append(Signal("new_52w_high", key, {"close": close}))
    elif prev.week52_low and close < prev.week52_low:
        out.append(Signal("new_52w_low", key, {"close": close}))

    if prev.nearest_resistance and close > prev.nearest_resistance and relvol >= _BREAKOUT_RELVOL:
        out.append(Signal("breakout", key, {"close": close, "level": prev.nearest_resistance}))
    elif prev.nearest_support and close < prev.nearest_support:
        out.append(Signal("breakdown", key, {"close": close, "level": prev.nearest_support}))

    if prev.above_sma_200 is False and today.above_sma_200 is True:
        out.append(Signal("ma200_cross_up", key, {"close": close}))
    elif prev.above_sma_200 is True and today.above_sma_200 is False:
        out.append(Signal("ma200_cross_down", key, {"close": close}))

    if prev.rsi_14 is not None and today.rsi_14 is not None:
        if prev.rsi_14 < 70 <= today.rsi_14:
            out.append(Signal("rsi_overbought", key, {"rsi": round(today.rsi_14)}))
        elif prev.rsi_14 > 30 >= today.rsi_14:
            out.append(Signal("rsi_oversold", key, {"rsi": round(today.rsi_14)}))
    return out


def _g(p: dict, k: str) -> str:
    v = p.get(k)
    return f"{v:g}" if isinstance(v, int | float) else "—"


# event_type -> (EN, BN). Each = a fact + a descriptive "what it means", never advice.
_TEMPLATES: dict[str, tuple[str, str]] = {
    "new_52w_high": (
        "{code} closed at a new 52-week high ({currency}{close}). The highest level in a year — a milestone, "
        "not a recommendation.",
        "{code} ৫২-সপ্তাহের নতুন সর্বোচ্চে ক্লোজ করেছে ({currency}{close})। এক বছরের সর্বোচ্চ — একটি মাইলফলক, "
        "কোনো পরামর্শ নয়।",
    ),
    "new_52w_low": (
        "{code} closed at a new 52-week low ({currency}{close}). The lowest level in a year — descriptive, "
        "not a recommendation.",
        "{code} ৫২-সপ্তাহের নতুন সর্বনিম্নে ক্লোজ করেছে ({currency}{close})। এক বছরের সর্বনিম্ন — তথ্যমূলক, "
        "কোনো পরামর্শ নয়।",
    ),
    "breakout": (
        "{code} closed above the {currency}{level} level it had been capped at — what technicians call a "
        "breakout, on above-average volume. A concept to watch, not a call.",
        "{code} {currency}{level} লেভেলের উপরে ক্লোজ করেছে যেখানে আগে আটকে ছিল — টেকনিশিয়ানরা একে ব্রেকআউট বলে, "
        "গড়ের বেশি ভলিউমে। দেখার মতো ধারণা, কোনো কল নয়।",
    ),
    "breakdown": (
        "{code} closed below the {currency}{level} support it had been holding. Technicians watch a broken "
        "support for the next level down. Descriptive, not advice.",
        "{code} {currency}{level} সাপোর্টের নিচে ক্লোজ করেছে যা ধরে রেখেছিল। ভাঙা সাপোর্টের পর পরের নিচের লেভেল "
        "দেখা হয়। তথ্যমূলক, পরামর্শ নয়।",
    ),
    "ma200_cross_up": (
        "{code} closed back above its 200-day average — often read as a longer-term trend turning "
        "up. A concept, not a forecast.",
        "{code} ২০০-দিনের গড়ের উপরে ফিরে ক্লোজ করেছে — প্রায়ই দীর্ঘমেয়াদি প্রবণতা ঊর্ধ্বমুখী হওয়া হিসেবে "
        "দেখা হয়। একটি ধারণা, ভবিষ্যদ্বাণী নয়।",
    ),
    "ma200_cross_down": (
        "{code} closed below its 200-day average — often read as a longer-term trend weakening. "
        "A concept, not a forecast.",
        "{code} ২০০-দিনের গড়ের নিচে ক্লোজ করেছে — প্রায়ই দীর্ঘমেয়াদি প্রবণতা দুর্বল হওয়া হিসেবে দেখা হয়। "
        "একটি ধারণা, ভবিষ্যদ্বাণী নয়।",
    ),
    "rsi_overbought": (
        "{code} moved into the overbought zone (RSI {rsi}). Historically moves can stall here — a "
        "concept to watch, not a forecast.",
        "{code} অতিরিক্ত কেনা জোনে গেছে (RSI {rsi})। সাধারণত এখানে মুভমেন্ট থমকে যেতে পারে — দেখার মতো "
        "ধারণা, ভবিষ্যদ্বাণী নয়।",
    ),
    "rsi_oversold": (
        "{code} moved into the oversold zone (RSI {rsi}). Historically selling can exhaust here — a "
        "concept to watch, not a forecast.",
        "{code} অতিরিক্ত বিক্রি জোনে গেছে (RSI {rsi})। সাধারণত এখানে বিক্রির চাপ কমে আসতে পারে — দেখার "
        "মতো ধারণা, ভবিষ্যদ্বাণী নয়।",
    ),
}


def render(sig: Signal, code: str, locale: str, currency: str = "৳") -> str:
    en, bn = _TEMPLATES[sig.event_type]
    tmpl = bn if locale == "bn" else en
    fields = {
        "code": code,
        "currency": currency,
        **{k: _g(sig.payload, k) for k in ("close", "level", "rsi")},
    }
    return tmpl.format(**fields)
