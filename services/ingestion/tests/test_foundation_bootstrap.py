from __future__ import annotations

import pytest

from ingestion import foundation_bootstrap


@pytest.mark.asyncio
async def test_bootstrap_all_advances_committed_batch_cursor(monkeypatch) -> None:
    calls: list[str | None] = []
    responses = [
        {
            "symbols": 2,
            "bars_seen": 20,
            "observations_inserted": 20,
            "next_after": "BBB",
        },
        {
            "symbols": 1,
            "bars_seen": 8,
            "observations_inserted": 6,
            "next_after": "CCC",
        },
    ]

    async def fake_batch(market, *, after, limit, pause_ms):
        calls.append(after)
        assert market == "US"
        assert limit == 2
        assert pause_ms == 0
        return responses.pop(0)

    monkeypatch.setattr(foundation_bootstrap, "bootstrap_daily_bars", fake_batch)

    result = await foundation_bootstrap.bootstrap_all_daily_bars(
        "US",
        batch_size=2,
        pause_ms=0,
    )

    assert calls == [None, "BBB"]
    assert result == {
        "market": "US",
        "symbols": 3,
        "bars_seen": 28,
        "observations_inserted": 26,
        "next_after": "CCC",
    }
