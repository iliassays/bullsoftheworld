"""Short-flow agent: flag days when a stock's short-sale share of volume runs well above its norm.

Data is FINRA's Reg SHO daily consolidated file. Framing matters: daily short volume counts every
sale marked short — including market-maker liquidity hedging — so it is NOT short interest and not
a "bearish bets" meter. Detection compares today's short share against the stock's own trailing
norm, with a liquidity floor and a history floor, and the copy always carries the caveat.
"""

from __future__ import annotations

from dataclasses import dataclass

BEAT = "shorts"
MIN_TOTAL_VOLUME = 100_000  # FINRA-reported shares — suppress tiny, unstable denominators
MIN_HISTORY_SESSIONS = 15  # need a real baseline before calling anything unusual
_MIN_RATIO = 0.55  # today's short share must be an outright majority of volume
_MIN_DEVIATION = 0.12  # and ≥ 12 points above the stock's own trailing norm
_MIN_Z_SCORE = 1.5  # today's ratio must also be statistically unusual when variance is available
_MIN_VOLUME_VS_NORM = 0.5  # ignore a ratio spike on a near-empty FINRA tape
MAX_NOTES_PER_DAY = 5  # cap the beat so the feed never floods


@dataclass
class ShortSignal:
    event_type: str
    occurrence_key: str
    ratio: float  # today's short share (0-1)
    avg_ratio: float  # trailing 20-session norm (0-1)
    z_score: float | None
    volume_vs_norm: float | None
    day: str


def detect(
    short_volume: float,
    total_volume: float,
    avg_ratio: float | None,
    ratio_stddev: float | None,
    avg_total_volume: float | None,
    history_sessions: int,
    day: str,
) -> ShortSignal | None:
    if total_volume < MIN_TOTAL_VOLUME or history_sessions < MIN_HISTORY_SESSIONS:
        return None
    if avg_ratio is None or not 0 < avg_ratio < 1:
        return None
    ratio = short_volume / total_volume
    if ratio < _MIN_RATIO or (ratio - avg_ratio) < _MIN_DEVIATION:
        return None
    z_score = (
        (ratio - avg_ratio) / ratio_stddev
        if ratio_stddev is not None and ratio_stddev > 0
        else None
    )
    if z_score is not None and z_score < _MIN_Z_SCORE:
        return None
    volume_vs_norm = total_volume / avg_total_volume if avg_total_volume else None
    if volume_vs_norm is not None and volume_vs_norm < _MIN_VOLUME_VS_NORM:
        return None
    return ShortSignal(
        "short_volume_elevated",
        day,
        ratio,
        avg_ratio,
        z_score,
        volume_vs_norm,
        day,
    )


_TEMPLATES = [
    (
        "{code}: {pct}% of FINRA-reported volume was marked short on {day}, versus a {avg}% "
        "20-session norm{context}. Daily short marks include market-maker hedging; this is unusual "
        "activity, not short interest or a bearish verdict. Descriptive, not advice."
    ),
    (
        "{code}: short-marked sales were {pct}% of FINRA-reported volume on {day} vs a {avg}% "
        "20-session norm{context}. This includes liquidity hedging and is neither whole-market "
        "volume nor short interest. Investigate the move; do not infer direction."
    ),
    (
        "Elevated short-sale share in {code} on {day}: {pct}% of FINRA-reported volume vs {avg}% "
        "typical{context}. Reg SHO marks include hedging, so treat this as an activity flag to "
        "investigate, not evidence of a bet against the company."
    ),
]


def render(sig: ShortSignal, code: str) -> str:
    template = _TEMPLATES[sum(ord(c) for c in code) % len(_TEMPLATES)]
    context = []
    if sig.z_score is not None:
        context.append(f"{sig.z_score:.1f} standard deviations above normal")
    if sig.volume_vs_norm is not None:
        context.append(f"reported activity {sig.volume_vs_norm:.1f}x normal")
    suffix = f" ({'; '.join(context)})" if context else ""
    return template.format(
        code=code,
        pct=round(sig.ratio * 100),
        avg=round(sig.avg_ratio * 100),
        context=suffix,
        day=sig.day,
    )
