import datetime as dt
from types import SimpleNamespace

from api.institutional_research.evidence import (
    EvidenceBundle,
    ReportedAccumulationEvidence,
)
from api.institutional_research.queue import (
    _load_evidence_by_analytics_cutoff,
    _research_clues,
)


def test_dse_clue_is_descriptive_and_keeps_publication_date_unknown() -> None:
    analytics = SimpleNamespace(
        market="DSE",
        pct_from_52w_low=4.0,
        as_of_date=dt.date(2026, 7, 31),
    )
    evidence = EvidenceBundle(
        reported_accumulation=ReportedAccumulationEvidence(
            market="DSE",
            report_date=dt.date(2026, 6, 30),
            prior_report_date=dt.date(2026, 5, 31),
            public_date=None,
            institutional_change_pp=0.4,
        )
    )

    clues = _research_clues(analytics, evidence)

    assert len(clues) == 1
    assert clues[0].key == "reported_accumulation_near_low"
    assert clues[0].public_as_of is None
    assert "category" in clues[0].limitations[0]
    assert "publication timestamp" in clues[0].limitations[1]


def test_us_clue_uses_manager_breadth_and_public_filing_date() -> None:
    analytics = SimpleNamespace(
        market="US",
        pct_from_52w_low=6.5,
        as_of_date=dt.date(2026, 7, 31),
    )
    evidence = EvidenceBundle(
        reported_accumulation=ReportedAccumulationEvidence(
            market="US",
            report_date=dt.date(2026, 6, 30),
            prior_report_date=dt.date(2026, 3, 31),
            public_date=dt.date(2026, 7, 25),
            adding_managers=9,
            reducing_managers=3,
            net_share_change=100_000,
            share_basis_comparable=True,
        )
    )

    clues = _research_clues(analytics, evidence)

    assert len(clues) == 1
    assert clues[0].public_as_of == dt.date(2026, 7, 25)
    assert "net breadth +50%" in clues[0].summary


def test_clue_does_not_appear_when_the_registered_evaluator_rejects_it() -> None:
    analytics = SimpleNamespace(
        market="US",
        pct_from_52w_low=6.5,
        as_of_date=dt.date(2026, 7, 31),
    )
    evidence = EvidenceBundle(
        reported_accumulation=ReportedAccumulationEvidence(
            market="US",
            report_date=dt.date(2026, 6, 30),
            prior_report_date=dt.date(2026, 3, 31),
            public_date=dt.date(2026, 7, 25),
            adding_managers=2,
            reducing_managers=8,
            net_share_change=100_000,
            share_basis_comparable=True,
        )
    )

    assert _research_clues(analytics, evidence) == []


async def test_evidence_loads_at_each_symbols_own_analytics_cutoff() -> None:
    calls: list[tuple[tuple[str, ...], dt.date]] = []

    class Adapter:
        async def load(self, _session, codes, *, cutoff):
            calls.append((tuple(codes), cutoff))
            return {code: EvidenceBundle() for code in codes}

    rows = [
        (object(), SimpleNamespace(code="FRESH", as_of_date=dt.date(2026, 7, 31))),
        (object(), SimpleNamespace(code="STALE", as_of_date=dt.date(2026, 7, 29))),
    ]
    result = await _load_evidence_by_analytics_cutoff(
        object(),
        adapter=Adapter(),
        rows=rows,
    )

    assert calls == [
        (("STALE",), dt.date(2026, 7, 29)),
        (("FRESH",), dt.date(2026, 7, 31)),
    ]
    assert set(result) == {"FRESH", "STALE"}
