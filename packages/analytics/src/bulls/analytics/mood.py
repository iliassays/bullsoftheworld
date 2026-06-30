"""Dhaka Mood Index — a market-wide 0-100 fear/greed read, assembled from facts we already compute.

Like `plain_read`: strictly deterministic and templated (no LLM, no drift), strictly descriptive (it
states what the breadth/strength/volatility data shows and how such a reading is generally
interpreted — never "buy" or "sell"). Each sub-index is normalised to 0-100 where 0 = extreme fear
and 100 = extreme greed. The overall score is the mean of whatever sub-indices we can actually
compute; anything we can't compute is omitted (omit over mislead) rather than guessed.

Bilingual (EN/BN): interpolated numbers stay Western numerals (matching the other deterministic
templates); the surrounding words are translated. `locale="bn"` selects Bangla.

Turnover-vs-average is deliberately NOT a scored axis: heavy turnover means greed on an up day but
fear on a panic-sell day, so its fear/greed direction is ambiguous. It rides along as descriptive
participation context instead.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from bulls.analytics.indicators import realized_volatility


class MoodComponent(BaseModel):
    key: str  # breadth | strength | highs_lows | volatility
    label: str  # localized
    score: int  # 0..100, fear → greed
    detail: str  # localized short value text, e.g. "259 ▲ / 72 ▼"


class MoodIndex(BaseModel):
    as_of_date: str
    score: int | None  # None when too few sub-indices are computable
    band: str  # extreme_fear | fear | neutral | greed | extreme_greed | unknown
    label: str  # localized band label
    components: list[MoodComponent]
    context: list[str]  # localized participation context (e.g. turnover)
    caption: str  # localized templated sentence
    disclaimer: str


# Band labels, calibrated so 50 = neutral.
_BANDS = [
    (25, "extreme_fear", "Extreme Fear", "চরম ভয়"),
    (45, "fear", "Fear", "ভয়"),
    (56, "neutral", "Neutral", "নিরপেক্ষ"),
    (75, "greed", "Greed", "লোভ"),
    (101, "extreme_greed", "Extreme Greed", "চরম লোভ"),
]

_COMPONENT_LABELS = {
    "breadth": ("Breadth", "ব্রেডথ"),
    "strength": ("Strength", "শক্তি"),
    "highs_lows": ("52-wk highs vs lows", "52-সপ্তাহ উচ্চ বনাম নিম্ন"),
    "volatility": ("Volatility", "অস্থিরতা"),
}

_DISCLAIMER = {
    "en": (
        "This describes the market's overall condition and how such a reading is generally "
        "interpreted — it is not a recommendation. Your decision and your risk are your own."
    ),
    "bn": (
        "এটি বাজারের সামগ্রিক অবস্থা এবং এমন একটি পাঠ সাধারণত কীভাবে বোঝা হয় তা বর্ণনা করে — "
        "এটি কোনো সুপারিশ নয়। সিদ্ধান্ত ও ঝুঁকি আপনার নিজের।"
    ),
}


def _clamp(x: float) -> int:
    return round(max(0.0, min(100.0, x)))


def _band(score: int, bn: bool) -> tuple[str, str]:
    for threshold, key, en_label, bn_label in _BANDS:
        if score < threshold:
            return key, (bn_label if bn else en_label)
    return "extreme_greed", ("চরম লোভ" if bn else "Extreme Greed")


def _breadth_score(adv: int, dec: int) -> float | None:
    decided = adv + dec
    return None if decided == 0 else adv / decided * 100


def _highs_lows_score(n_high: int, n_low: int) -> float | None:
    extremes = n_high + n_low
    return None if extremes == 0 else n_high / extremes * 100


def _volatility_score(closes: Sequence[float]) -> float | None:
    """Recent realised vol vs a longer baseline, inverted: calmer than usual = greed, more turbulent
    = fear. Returns None until there's enough DSEX history for both windows."""
    recent = realized_volatility(closes, period=20)
    baseline = realized_volatility(closes, period=100)
    if recent is None or not baseline:
        return None
    ratio = recent / baseline
    # ratio 1.0 → 50 (normal); 0.5 → ~80 (calm/greed); 1.5 → ~20 (turbulent/fear).
    return _clamp(50 - (ratio - 1) * 60)


def _caption(band: str, top: MoodComponent | None, bn: bool) -> str:
    drivers = {
        "breadth": ("most shares are rising", "অধিকাংশ শেয়ার বাড়ছে"),
        "strength": ("most shares hold above their long-term average", "অধিকাংশ শেয়ার দীর্ঘমেয়াদি গড়ের উপরে"),
        "highs_lows": ("more shares are near 52-week highs than lows", "নিম্নের তুলনায় বেশি শেয়ার 52-সপ্তাহের উচ্চের কাছে"),
        "volatility": ("day-to-day swings are calm", "দৈনিক ওঠানামা শান্ত"),
    }
    fear_drivers = {
        "breadth": ("most shares are falling", "অধিকাংশ শেয়ার কমছে"),
        "strength": ("most shares sit below their long-term average", "অধিকাংশ শেয়ার দীর্ঘমেয়াদি গড়ের নিচে"),
        "highs_lows": ("more shares are near 52-week lows than highs", "উচ্চের তুলনায় বেশি শেয়ার 52-সপ্তাহের নিম্নের কাছে"),
        "volatility": ("day-to-day swings are large", "দৈনিক ওঠানামা বড়"),
    }
    greedy = band in ("greed", "extreme_greed")
    fearful = band in ("fear", "extreme_fear")
    if top is None or band == "unknown":
        return "বাজারের মন বোঝার মতো যথেষ্ট তথ্য নেই।" if bn else "Not enough data to read the market's mood."
    pool = drivers if top.score >= 50 else fear_drivers
    reason = pool[top.key][1 if bn else 0]
    if greedy:
        return (f"বাজারে এখন লোভের আবহ — {reason}।" if bn else f"The market mood is greedy — {reason}.")
    if fearful:
        return (f"বাজারে এখন ভয়ের আবহ — {reason}।" if bn else f"The market mood is fearful — {reason}.")
    return (f"বাজারের মন এখন মোটামুটি ভারসাম্যে — {reason}।" if bn
            else f"The market mood is fairly balanced — {reason}.")


def build_mood(
    *,
    as_of_date: str,
    locale: str = "en",
    advancers: int = 0,
    decliners: int = 0,
    pct_above_200dma: float | None = None,  # 0..1 fraction of the liquid universe
    n_near_52w_high: int = 0,
    n_near_52w_low: int = 0,
    dsex_closes: Sequence[float] | None = None,  # ascending DSEX closes for the volatility read
    turnover_vs_20d: float | None = None,  # context only, not scored
    min_components: int = 2,
) -> MoodIndex:
    """Assemble the market-mood reading. Sub-indices that can't be computed are omitted; if fewer
    than `min_components` survive, the score is None (we don't fake a mood from thin data)."""
    bn = locale == "bn"
    raw = {
        "breadth": _breadth_score(advancers, decliners),
        "strength": None if pct_above_200dma is None else pct_above_200dma * 100,
        "highs_lows": _highs_lows_score(n_near_52w_high, n_near_52w_low),
        "volatility": _volatility_score(dsex_closes or []),
    }
    details = {
        "breadth": f"{advancers} ▲ / {decliners} ▼",
        "strength": None if pct_above_200dma is None else f"{pct_above_200dma * 100:.0f}% > 200-DMA",
        "highs_lows": f"{n_near_52w_high} ⤴ / {n_near_52w_low} ⤵",
        "volatility": ("শান্ত" if bn else "calm") if (raw["volatility"] or 0) >= 50 else ("উত্থানপতন" if bn else "turbulent"),
    }
    components = [
        MoodComponent(
            key=key,
            label=_COMPONENT_LABELS[key][1 if bn else 0],
            score=_clamp(score),
            detail=details[key] or "",
        )
        for key, score in raw.items()
        if score is not None
    ]

    context: list[str] = []
    if turnover_vs_20d is not None:
        context.append(
            f"টার্নওভার {turnover_vs_20d:.1f}x গড়" if bn else f"Turnover {turnover_vs_20d:.1f}x avg"
        )

    if len(components) < min_components:
        return MoodIndex(
            as_of_date=as_of_date,
            score=None,
            band="unknown",
            label="অজানা" if bn else "Unknown",
            components=components,
            context=context,
            caption=_caption("unknown", None, bn),
            disclaimer=_DISCLAIMER["bn" if bn else "en"],
        )

    score = _clamp(sum(c.score for c in components) / len(components))
    band, label = _band(score, bn)
    top = max(components, key=lambda c: abs(c.score - 50))
    return MoodIndex(
        as_of_date=as_of_date,
        score=score,
        band=band,
        label=label,
        components=components,
        context=context,
        caption=_caption(band, top, bn),
        disclaimer=_DISCLAIMER["bn" if bn else "en"],
    )
