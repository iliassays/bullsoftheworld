from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ingestion import scheduler


class _AsyncContext:
    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Session:
    def __init__(self):
        self.commit = AsyncMock()
        self.savepoints = 0

    def begin_nested(self):
        self.savepoints += 1
        return _AsyncContext()


class _Redis:
    def __init__(self):
        self.aclose = AsyncMock()


@pytest.mark.asyncio
async def test_intraday_failure_rolls_back_savepoint_but_quote_ingestion_continues(
    monkeypatch,
) -> None:
    quote = SimpleNamespace(code="AAA", ltp=10.0, market="DSE")
    symbol = SimpleNamespace(code="AAA", market="DSE")
    provider = SimpleNamespace(
        list_symbols=AsyncMock(return_value=[symbol]),
        get_quotes=AsyncMock(return_value=[quote]),
    )
    session = _Session()
    redis = _Redis()
    upsert_symbols = AsyncMock()
    upsert_quotes = AsyncMock()
    alerts = AsyncMock()
    publish = AsyncMock()
    capture = AsyncMock(side_effect=RuntimeError("intraday table unavailable"))

    monkeypatch.setattr(scheduler, "get_provider", lambda market: provider)
    monkeypatch.setattr(scheduler, "get_sessionmaker", lambda: lambda: _AsyncContext(session))
    monkeypatch.setattr(scheduler, "bind_tenant_context", AsyncMock())
    monkeypatch.setattr(scheduler, "_upsert_symbols", upsert_symbols)
    monkeypatch.setattr(scheduler, "_upsert_quotes", upsert_quotes)
    monkeypatch.setattr(scheduler, "check_price_alerts", alerts)
    monkeypatch.setattr(scheduler, "persist_intraday_capture", capture)
    monkeypatch.setattr(scheduler, "_publish_ticks", publish)
    monkeypatch.setattr(scheduler.aioredis, "from_url", lambda url: redis)
    monkeypatch.setattr(
        scheduler,
        "get_settings",
        lambda: SimpleNamespace(redis_url="redis://unused"),
    )

    result = await scheduler.poll_market("DSE", tenant_id="bullsofdhaka")

    assert session.savepoints == 1
    upsert_quotes.assert_awaited_once_with(session, [quote])
    alerts.assert_awaited_once()
    session.commit.assert_awaited_once()
    publish.assert_awaited_once_with(redis, [quote])
    redis.aclose.assert_awaited_once()
    assert result == {"symbols": 1, "quotes": 1, "intraday_capture_failures": 1}


@pytest.mark.asyncio
async def test_intraday_capture_success_reports_no_isolated_failure(monkeypatch) -> None:
    session = _Session()
    capture = AsyncMock(return_value=None)
    monkeypatch.setattr(scheduler, "persist_intraday_capture", capture)

    failures = await scheduler._persist_intraday_isolated(
        session,
        [],
        expected_symbol_count=0,
    )

    assert failures == 0
    assert session.savepoints == 1
