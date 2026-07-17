from __future__ import annotations

import datetime as dt

from api.institutional_research.lineage import build_evidence_source_snapshots
from api.institutional_research.schemas import EvidenceItemOut
from bulls.analytics.research_loop import AutonomousResearchInput, ResearchFact


def _payload() -> AutonomousResearchInput:
    return AutonomousResearchInput(
        market="US",
        code="NXTC",
        company="NextCure, Inc.",
        knowledge_cutoff_at="2026-07-16T22:30:00Z",
        quality=50,
        value=50,
        momentum=50,
        risk=50,
        novelty=50,
        quality_confidence=1,
        value_confidence=1,
        momentum_confidence=1,
        risk_confidence=1,
        evidence_coverage_pct=100,
        official_evidence_count=1,
        average_daily_value_mn=2,
        capacity_mn=None,
        cap_tier="small",
        facts=[
            ResearchFact(
                key="market_data_as_of_date",
                label="Market Data As Of Date",
                value="2026-07-16",
                source_kind="market_data",
                source_id="ticker-analytics:US:NXTC:2026-07-16",
            ),
            ResearchFact(
                key="last_price",
                label="Last Price",
                value=12.5,
                source_kind="market_data",
                source_id="ticker-analytics:US:NXTC:2026-07-16",
            ),
            ResearchFact(
                key="latest_official_evidence",
                label="Latest Official Evidence",
                value="10-Q filing",
                source_kind="official_evidence",
                source_id="sec:0001234567-26-000001",
            ),
        ],
    )


def test_evidence_snapshots_group_facts_and_preserve_official_metadata() -> None:
    payload = _payload()
    evidence = EvidenceItemOut(
        id="sec:0001234567-26-000001",
        source="SEC EDGAR",
        title="10-Q filing",
        published_at=dt.date(2026, 7, 15),
        url="https://www.sec.gov/Archives/example",
    )

    first = build_evidence_source_snapshots(payload, evidence_items=[evidence])
    second = build_evidence_source_snapshots(payload, evidence_items=[evidence])

    assert first == second
    assert len(first) == 2
    analytics, filing = first
    assert analytics.source_type == "ticker_analytics"
    assert analytics.effective_at == dt.datetime(2026, 7, 16, tzinfo=dt.UTC)
    assert [span.fact_key for span in analytics.spans] == [
        "market_data_as_of_date",
        "last_price",
    ]
    assert filing.source_type == "sec_filing"
    assert filing.source_url == "https://www.sec.gov/Archives/example"
    assert filing.published_at == dt.datetime(2026, 7, 15, tzinfo=dt.UTC)
    assert filing.content_hash == filing.source_revision


def test_evidence_snapshot_hash_changes_when_a_registered_fact_changes() -> None:
    original = _payload()
    changed = original.model_copy(
        update={
            "facts": [
                fact.model_copy(update={"value": 13.0}) if fact.key == "last_price" else fact
                for fact in original.facts
            ]
        }
    )

    original_snapshot = build_evidence_source_snapshots(original, evidence_items=[])[0]
    changed_snapshot = build_evidence_source_snapshots(changed, evidence_items=[])[0]

    assert original_snapshot.content_hash != changed_snapshot.content_hash
    assert original_snapshot.source_revision != changed_snapshot.source_revision
