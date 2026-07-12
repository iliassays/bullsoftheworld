"""Audited manager identities whose disclosed exposure must survive bounded 13F retention."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WatchedManager:
    cik: int
    name: str
    style: str
    interpretation: str


WATCHED_MANAGERS: dict[int, WatchedManager] = {
    1_423_053: WatchedManager(
        cik=1_423_053,
        name="Citadel Advisors LLC",
        style="quantitative_market_maker",
        interpretation=(
            "Reported quarter-end long exposure may reflect inventory or hedging and is not "
            "evidence of directional conviction."
        ),
    ),
    1_533_421: WatchedManager(
        cik=1_533_421,
        name="Tower Research Capital LLC (TRC)",
        style="quantitative_market_maker",
        interpretation=(
            "Reported quarter-end long exposure may reflect high-turnover market-making activity "
            "and is not an entry signal."
        ),
    ),
}
WATCHED_MANAGER_CIKS = frozenset(WATCHED_MANAGERS)
