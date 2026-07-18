from __future__ import annotations

import datetime as dt
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from api.institutional_research.portfolio import (
    _accounting_event_hash,
    _record_accounting_events,
)
from bulls.analytics.research_strategy import opening_accounting_events
from bulls.core.models import ResearchAccountingEvent


def _portfolio() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        tenant_id="bullsofdhaka",
        market="DSE",
    )


@pytest.mark.asyncio
async def test_accounting_events_are_persisted_without_a_snapshot_dependency() -> None:
    rows = SimpleNamespace(all=lambda: [])
    session = SimpleNamespace(
        execute=AsyncMock(return_value=rows),
        scalar=AsyncMock(return_value=None),
        add=Mock(),
        flush=AsyncMock(),
    )
    events = opening_accounting_events(
        initial_capital=100_000,
        effective_date=dt.date(2026, 7, 18),
    )

    await _record_accounting_events(
        session,
        portfolio=_portfolio(),
        events=events,
    )

    persisted = session.add.call_args.args[0]
    assert isinstance(persisted, ResearchAccountingEvent)
    assert persisted.event_key == "s0:opening_balance"
    assert persisted.sequence == 0
    assert persisted.payload_hash == _accounting_event_hash(events[0])
    assert "snapshot_id" not in persisted.__table__.c


@pytest.mark.asyncio
async def test_accounting_retry_rejects_same_key_with_changed_economic_payload() -> None:
    events = opening_accounting_events(
        initial_capital=100_000,
        effective_date=dt.date(2026, 7, 18),
    )
    rows = SimpleNamespace(all=lambda: [(events[0].event_key, "0" * 64)])
    session = SimpleNamespace(
        execute=AsyncMock(return_value=rows),
        scalar=AsyncMock(return_value=0),
        add=Mock(),
        flush=AsyncMock(),
    )

    with pytest.raises(RuntimeError, match="different economic identity"):
        await _record_accounting_events(
            session,
            portfolio=_portfolio(),
            events=events,
        )

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_accounting_retry_with_identical_payload_is_a_noop() -> None:
    events = opening_accounting_events(
        initial_capital=100_000,
        effective_date=dt.date(2026, 7, 18),
    )
    rows = SimpleNamespace(
        all=lambda: [(events[0].event_key, _accounting_event_hash(events[0]))]
    )
    session = SimpleNamespace(
        execute=AsyncMock(return_value=rows),
        scalar=AsyncMock(return_value=0),
        add=Mock(),
        flush=AsyncMock(),
    )

    await _record_accounting_events(
        session,
        portfolio=_portfolio(),
        events=events,
    )

    session.add.assert_not_called()
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_accounting_retry_rejects_same_key_moved_to_another_session() -> None:
    original = opening_accounting_events(
        initial_capital=100_000,
        effective_date=dt.date(2026, 7, 18),
    )[0]
    moved = original.model_copy(update={"effective_date": dt.date(2026, 7, 19)})
    rows = SimpleNamespace(
        all=lambda: [(original.event_key, _accounting_event_hash(original))]
    )
    session = SimpleNamespace(
        execute=AsyncMock(return_value=rows),
        scalar=AsyncMock(return_value=0),
        add=Mock(),
        flush=AsyncMock(),
    )

    with pytest.raises(RuntimeError, match="different economic identity"):
        await _record_accounting_events(
            session,
            portfolio=_portfolio(),
            events=[moved],
        )
