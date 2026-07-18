from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.dialects import postgresql

from ingestion import analytics, restricted_research, sec_worker


async def test_analytics_rejects_unbounded_restricted_scope() -> None:
    with pytest.raises(ValueError, match="explicit non-empty code list"):
        await analytics.compute_all("US", include_restricted=True)


async def test_restricted_refresh_is_explicit_and_does_not_publish_agents(monkeypatch) -> None:
    history_calls: list[dict] = []
    analytics_calls: list[dict] = []
    quote_calls: list[dict] = []

    async def fake_codes() -> list[str]:
        return ["NVVE", "SOBR"]

    async def fake_private_codes(session_date: dt.date) -> list[str]:
        assert isinstance(session_date, dt.date)
        return ["AAPL", "NVVE"]

    async def fake_history(market: str, **kwargs):
        history_calls.append({"market": market, **kwargs})
        return {"bars_upserted": 10}

    async def fake_analytics(market: str, **kwargs):
        analytics_calls.append({"market": market, **kwargs})
        return {"computed": 2}

    async def fake_quotes(**kwargs):
        quote_calls.append(kwargs)
        return 2

    monkeypatch.setattr(restricted_research, "restricted_research_codes", fake_codes)
    monkeypatch.setattr(restricted_research, "stale_private_research_codes", fake_private_codes)
    monkeypatch.setattr(restricted_research, "collect_history", fake_history)
    monkeypatch.setattr(restricted_research, "compute_all", fake_analytics)
    monkeypatch.setattr(restricted_research, "publish_quotes", fake_quotes)

    result = await restricted_research.refresh_restricted_market_data()

    assert result["symbols"] == 3
    assert result["private_symbols"] == 2
    assert result["restricted_symbols"] == 2
    assert history_calls[0]["codes"] == ["AAPL", "NVVE", "SOBR"]
    assert history_calls[0]["include_reference"] is True
    assert analytics_calls[0]["codes"] == ["AAPL", "NVVE", "SOBR"]
    assert analytics_calls[0]["include_onboarding"] is True
    assert analytics_calls[0]["include_restricted"] is True
    assert quote_calls == [{"codes": ["AAPL", "NVVE", "SOBR"]}]
    assert result["quotes"] == 2


def test_private_refresh_selects_only_stale_non_public_research_symbols() -> None:
    statement = restricted_research._stale_private_research_stmt(
        dt.date(2026, 7, 17),
        limit=1_500,
    )
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "symbols.data_status != 'ready'" in sql
    assert "symbols.research_status IN ('ready', 'partial')" in sql
    assert "symbols.data_last_date < '2026-07-17'" in sql
    assert "security_master.is_product_eligible IS true" in sql
    assert "LIMIT 1500" in sql


async def test_restricted_sec_failure_does_not_block_public_agents(monkeypatch) -> None:
    notes_ran = False

    async def fake_sec(*, codes=None):
        assert codes is None
        return {"symbols": 100}

    async def failed_restricted_codes() -> list[str]:
        raise RuntimeError("restricted lookup failed")

    async def fake_notes(*, tenant_id: str):
        nonlocal notes_ran
        notes_ran = True
        return {"published": 3, "tenant_id": tenant_id}

    monkeypatch.setattr(sec_worker, "refresh_sec_evidence", fake_sec)
    monkeypatch.setattr(sec_worker, "restricted_research_codes", failed_restricted_codes)
    monkeypatch.setattr(sec_worker, "run_sec_filing_agents", fake_notes)

    result = await sec_worker.refresh_sec_company_data({})

    assert notes_ran is True
    assert "restricted={'failed': 'RuntimeError'}" in result
    assert "published" in result
