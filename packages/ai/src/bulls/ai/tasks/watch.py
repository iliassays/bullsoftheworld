"""Today's Watch — an AI note highlighting notable stocks from the day's activity.

Like the digest: the caller computes the ranked facts (movers + chatter) in code; the LLM only
writes the prose naming them. One LLM call for the whole note (cheap, cacheable daily).
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from bulls.ai.compliance import contains_advice
from bulls.ai.llm import structured_complete
from bulls.ai.prompts.watch import WATCH_SYSTEM_V1

log = logging.getLogger(__name__)


class WatchItem(BaseModel):
    code: str
    change_pct: float
    posts: int
    bull: int
    bear: int


class Breadth(BaseModel):
    """Market-wide up/down tally for the session."""

    advancers: int
    decliners: int
    unchanged: int
    total: int


class WatchOut(BaseModel):
    summary: str


def _render(items: list[WatchItem], breadth: Breadth | None) -> str:
    lines: list[str] = []
    if breadth and breadth.total:
        lines.append(
            f"Market breadth: {breadth.advancers} up, {breadth.decliners} down, "
            f"{breadth.unchanged} unchanged (of {breadth.total} traded)."
        )
    lines.append("Active / moving stocks:")
    for it in items:
        lines.append(
            f"- {it.code}: {it.change_pct:+.2f}%, {it.posts} posts "
            f"({it.bull} bull / {it.bear} bear)"
        )
    return "\n".join(lines)


def _fallback(items: list[WatchItem]) -> str:
    """Deterministic, advice-free note if the model trips the compliance gate."""
    top = sorted(items, key=lambda i: abs(i.change_pct), reverse=True)[:3]
    return "Movers: " + ", ".join(f"${i.code} {i.change_pct:+.1f}%" for i in top)


async def todays_watch(
    items: list[WatchItem], *, breadth: Breadth | None = None, language: str = "English"
) -> str:
    """Grounded 2-3 sentence watch note in the requested language.

    Output passes the no-advice compliance gate; anything advisory is replaced with a safe
    deterministic movers list.
    """
    if not items:
        return ""
    system = f"{WATCH_SYSTEM_V1}\n\nWrite the note in {language}."
    result = await structured_complete(system, _render(items, breadth), WatchOut)
    summary = result.summary.strip()

    if contains_advice(summary).is_advice:
        log.warning("today's watch tripped no-advice gate; using fallback")
        return _fallback(items)
    return summary
