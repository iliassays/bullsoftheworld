"""Symbol digest — fuse price action + crowd sentiment into a grounded one-liner.

The caller computes the FACTS (price stats, sentiment tally) in code; the LLM only writes prose
from them. That keeps numbers correct and the model from hallucinating. `crowd_mood` is derived
deterministically here, not by the model.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

from bulls.ai.compliance import contains_advice
from bulls.ai.llm import structured_complete
from bulls.ai.prompts.digest import DIGEST_SYSTEM_V1

log = logging.getLogger(__name__)

Mood = Literal["bullish", "bearish", "mixed", "quiet"]


class SymbolFacts(BaseModel):
    code: str
    name: str
    last_price: float
    change_pct_1d: float
    change_pct_5d: float | None = None
    last_volume: int
    avg_volume_5d: int | None = None
    bull_posts: int = 0
    bear_posts: int = 0
    neutral_posts: int = 0
    sample_posts: list[str] = []
    is_delayed: bool = True

    # Computed technicals (from bulls.analytics) — descriptive facts, optional.
    rsi_14: float | None = None
    above_sma_50: bool | None = None
    above_sma_200: bool | None = None
    nearest_support: float | None = None
    nearest_resistance: float | None = None
    pct_from_52w_high: float | None = None


class DigestOut(BaseModel):
    summary: str


def crowd_mood(bull: int, bear: int, neutral: int) -> Mood:
    """Deterministic mood from the tally — not the model's job."""
    total = bull + bear + neutral
    if total == 0:
        return "quiet"
    lean = (bull - bear) / total
    if lean >= 0.3:
        return "bullish"
    if lean <= -0.3:
        return "bearish"
    return "mixed"


def _render(facts: SymbolFacts) -> str:
    total = facts.bull_posts + facts.bear_posts + facts.neutral_posts
    lines = [
        f"Stock: ${facts.code} ({facts.name})",
        f"Last price: {facts.last_price} ({facts.change_pct_1d:+.2f}% today)"
        + ("  [15-min delayed]" if facts.is_delayed else ""),
    ]
    if facts.change_pct_5d is not None:
        lines.append(f"5-day change: {facts.change_pct_5d:+.2f}%")
    if facts.avg_volume_5d:
        rel = facts.last_volume / facts.avg_volume_5d if facts.avg_volume_5d else 1
        lines.append(
            f"Volume: {facts.last_volume:,} vs 5-day avg {facts.avg_volume_5d:,} ({rel:.1f}x)"
        )
    if total:
        lines.append(
            f"Crowd (last 7 days): {total} posts — {facts.bull_posts} bull, "
            f"{facts.bear_posts} bear, {facts.neutral_posts} neutral"
        )
        if facts.sample_posts:
            lines.append("Recent posts:")
            lines += [f'  - "{p}"' for p in facts.sample_posts]
    else:
        lines.append("Crowd (last 7 days): no posts.")

    tech: list[str] = []
    if facts.rsi_14 is not None:
        tech.append(f"RSI(14) {facts.rsi_14:.0f}")
    if facts.above_sma_50 is not None:
        tech.append("above 50-day avg" if facts.above_sma_50 else "below 50-day avg")
    if facts.above_sma_200 is not None:
        tech.append("above 200-day avg" if facts.above_sma_200 else "below 200-day avg")
    if facts.nearest_support is not None:
        tech.append(f"nearest support ~{facts.nearest_support}")
    if facts.nearest_resistance is not None:
        tech.append(f"nearest resistance ~{facts.nearest_resistance}")
    if facts.pct_from_52w_high is not None and facts.pct_from_52w_high < -0.5:
        tech.append(f"{abs(facts.pct_from_52w_high):.0f}% below its 52-week high")
    if tech:
        lines.append("Technicals (end-of-day): " + "; ".join(tech))
    return "\n".join(lines)


def _safe_fallback(facts: SymbolFacts) -> str:
    """Deterministic, advice-free one-liner — used if the model trips the compliance gate."""
    total = facts.bull_posts + facts.bear_posts + facts.neutral_posts
    parts = [f"${facts.code} — {facts.last_price} ({facts.change_pct_1d:+.2f}%)"]
    if total:
        parts.append(f"{total} posts ({facts.bull_posts}▲/{facts.bear_posts}▼)")
    return " · ".join(parts)


async def summarize_symbol(facts: SymbolFacts, *, language: str = "English") -> str:
    """Return a grounded one/two-sentence digest string in the requested language.

    The output passes the no-advice compliance gate; anything that trips it is replaced with a
    safe deterministic summary rather than shown to a user.
    """
    system = f"{DIGEST_SYSTEM_V1}\n\nWrite the digest in {language}."
    result = await structured_complete(system, _render(facts), DigestOut)
    summary = result.summary.strip()

    finding = contains_advice(summary)
    if finding.is_advice:
        log.warning("digest tripped no-advice gate for $%s: %s", facts.code, finding.matches)
        return _safe_fallback(facts)
    return summary
