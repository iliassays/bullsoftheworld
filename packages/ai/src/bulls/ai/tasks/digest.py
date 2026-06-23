"""Symbol digest — fuse price action + crowd sentiment into a grounded one-liner.

The caller computes the FACTS (price stats, sentiment tally) in code; the LLM only writes prose
from them. That keeps numbers correct and the model from hallucinating. `crowd_mood` is derived
deterministically here, not by the model.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from bulls.ai.llm import structured_complete
from bulls.ai.prompts.digest import DIGEST_SYSTEM_V1

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
    return "\n".join(lines)


async def summarize_symbol(facts: SymbolFacts, *, language: str = "English") -> str:
    """Return a grounded one/two-sentence digest string in the requested language."""
    system = f"{DIGEST_SYSTEM_V1}\n\nWrite the digest in {language}."
    result = await structured_complete(system, _render(facts), DigestOut)
    return result.summary.strip()
