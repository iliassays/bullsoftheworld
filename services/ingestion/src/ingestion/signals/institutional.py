"""Material Form 13F change detection for the U.S. institutional desk.

13F data is delayed, quarter-end long exposure. A useful signal needs agreement between aggregate
reported shares and manager breadth; one large custodial or market-maker position is not enough.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

BEAT = "institution"
MAX_NOTES_PER_RUN = 10


@dataclass(frozen=True)
class InstitutionalSignal:
    event_type: str
    occurrence_key: str
    direction: str
    net_change_pct: float
    breadth_pct: float
    managers_count: int
    adding_managers: int
    reducing_managers: int
    report_date: dt.date
    public_by: dt.date
    evidence: str
    watched_managers: tuple[str, ...]

    @property
    def rank(self) -> float:
        confirmation = 20 if self.evidence == "confirmed" else 0
        watched = min(len(self.watched_managers), 2) * 3
        return abs(self.net_change_pct) + abs(self.breadth_pct) / 2 + confirmation + watched


def detect(
    *,
    report_date: dt.date,
    public_by: dt.date,
    managers_count: int,
    net_change_pct: float | None,
    new_positions: int,
    increased_positions: int,
    reduced_positions: int,
    exited_positions: int,
    unchanged_positions: int,
    watched_managers: tuple[str, ...] = (),
) -> InstitutionalSignal | None:
    if net_change_pct is None or managers_count < 3:
        return None
    adding = new_positions + increased_positions
    reducing = reduced_positions + exited_positions
    classified = adding + reducing + unchanged_positions
    if classified < 5:
        return None
    breadth = (adding - reducing) / classified * 100
    same_direction = (net_change_pct > 0 and breadth > 0) or (
        net_change_pct < 0 and breadth < 0
    )
    material = abs(net_change_pct) >= 15 and abs(breadth) >= 20
    very_large = abs(net_change_pct) >= 30 and abs(breadth) >= 10
    if not ((material and same_direction) or very_large):
        return None
    direction = "increased" if net_change_pct > 0 else "reduced"
    return InstitutionalSignal(
        event_type=f"13f_reported_shares_{direction}",
        occurrence_key=str(report_date),
        direction=direction,
        net_change_pct=net_change_pct,
        breadth_pct=breadth,
        managers_count=managers_count,
        adding_managers=adding,
        reducing_managers=reducing,
        report_date=report_date,
        public_by=public_by,
        evidence="confirmed" if same_direction else "mixed",
        watched_managers=watched_managers,
    )


def render(signal: InstitutionalSignal, code: str) -> str:
    direction = "rose" if signal.direction == "increased" else "fell"
    watched = ""
    if signal.watched_managers:
        watched = (
            f" Watched quant/market-making filers present: {', '.join(signal.watched_managers)}; "
            "their exposure can be inventory or hedging, not conviction."
        )
    return (
        f"{code}: aggregate reported 13F shares {direction} {abs(signal.net_change_pct):.1f}% "
        f"for the quarter ended {signal.report_date}. Manager breadth was {signal.breadth_pct:+.0f}% "
        f"({signal.adding_managers} adding vs {signal.reducing_managers} reducing), so the evidence "
        f"is {signal.evidence}.{watched} These are delayed quarter-end long holdings, public by "
        f"{signal.public_by}; they do not reveal trade dates, shorts, or intent. Descriptive, not advice."
    )
