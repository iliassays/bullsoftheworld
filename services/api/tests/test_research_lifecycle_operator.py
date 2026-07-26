from __future__ import annotations

import datetime as dt
import uuid

import pytest

from api.institutional_research.operator import (
    ForwardShadowOperatorRequest,
    HistoricalReplayOperatorRequest,
    LifecycleOperatorRequest,
    PauseShadowBookOperatorRequest,
    _argument_parser,
    _forward_seed_idempotency_key,
    configure_lifecycle,
    pause_shadow_book,
    seed_historical_replay,
)
from api.institutional_research.worker import (
    lifecycle_execution_trigger,
    lifecycle_freshness_error,
)


def test_forward_operator_cli_wires_empty_book_replacement_flag() -> None:
    arguments = _argument_parser().parse_args(
        [
            "forward",
            "--tenant",
            "bullsofdhaka",
            "--handle",
            "ilias",
            "--strategy",
            "dse_compression_breakout_20d_v1",
            "--initial-capital",
            "10000000",
            "--replace-empty",
            "--apply",
        ]
    )

    request = ForwardShadowOperatorRequest(
        tenant=arguments.tenant,
        handle=arguments.handle,
        strategy_key=arguments.strategy,
        initial_capital=arguments.initial_capital,
        universe_limit=arguments.universe_limit,
        cap_tier=arguments.cap_tier,
        replace_empty=arguments.replace_empty,
        apply=arguments.apply,
    )

    assert request.replace_empty is True
    assert request.apply is True


def test_pause_book_cli_binds_exact_portfolio_and_reason() -> None:
    portfolio_id = uuid.uuid4()
    arguments = _argument_parser().parse_args(
        [
            "pause-book",
            "--tenant",
            "bullsofdhaka",
            "--handle",
            "ilias",
            "--portfolio-id",
            str(portfolio_id),
            "--reason",
            "Historical diagnostic failed its registered evidence gates.",
            "--apply",
        ]
    )

    assert arguments.portfolio_id == portfolio_id
    assert arguments.apply is True


def test_forward_seed_key_is_bounded_and_changes_with_methodology() -> None:
    first = _forward_seed_idempotency_key(
        strategy_key="x" * 48,
        methodology_version="methodology-v1",
        latest_date=dt.date(2026, 7, 26),
        cap_tier="unclassified",
        universe_limit=500,
    )
    second = _forward_seed_idempotency_key(
        strategy_key="x" * 48,
        methodology_version="methodology-v2",
        latest_date=dt.date(2026, 7, 26),
        cap_tier="unclassified",
        universe_limit=500,
    )

    assert len(first) <= 96
    assert first != second


def test_scheduled_attempts_share_one_session_trigger() -> None:
    first = lifecycle_execution_trigger(
        "scheduled:first-attempt",
        scheduled=True,
        market="DSE",
        latest_bar=dt.date(2026, 7, 15),
        latest_analytics=dt.date(2026, 7, 15),
    )
    retry = lifecycle_execution_trigger(
        "scheduled:retry",
        scheduled=True,
        market="DSE",
        latest_bar=dt.date(2026, 7, 15),
        latest_analytics=dt.date(2026, 7, 15),
    )

    assert first == retry == "session:DSE:2026-07-15"


def test_dse_squeeze_book_waits_for_same_session_forward_archive() -> None:
    expected = dt.date(2026, 7, 27)

    stale = lifecycle_freshness_error(
        expected_session=expected,
        latest_bar=expected,
        latest_analytics=expected,
        squeeze_archive_required=True,
        latest_squeeze_archive=expected - dt.timedelta(days=1),
    )
    ready = lifecycle_freshness_error(
        expected_session=expected,
        latest_bar=expected,
        latest_analytics=expected,
        squeeze_archive_required=True,
        latest_squeeze_archive=expected,
    )

    assert stale is not None
    assert "waiting for DSE squeeze archive" in stale
    assert ready is None


def test_non_squeeze_workspace_does_not_wait_for_squeeze_archive() -> None:
    expected = dt.date(2026, 7, 27)

    assert (
        lifecycle_freshness_error(
            expected_session=expected,
            latest_bar=expected,
            latest_analytics=expected,
            squeeze_archive_required=False,
            latest_squeeze_archive=None,
        )
        is None
    )


def test_operator_attempt_retains_unique_trigger() -> None:
    assert (
        lifecycle_execution_trigger(
            "operator:forced-rerun",
            scheduled=False,
            market="DSE",
            latest_bar=dt.date(2026, 7, 15),
            latest_analytics=dt.date(2026, 7, 15),
        )
        == "operator:forced-rerun"
    )


@pytest.mark.asyncio
async def test_operator_requires_explicit_apply_acknowledgement() -> None:
    with pytest.raises(RuntimeError, match="without --apply"):
        await configure_lifecycle(
            LifecycleOperatorRequest(
                tenant="bullsofdhaka",
                handle="analyst",
                strategy_key="dse_reversal_v1",
                initial_capital=10_000_000,
            )
        )


@pytest.mark.asyncio
async def test_pause_operator_requires_explicit_apply_acknowledgement() -> None:
    with pytest.raises(RuntimeError, match="without --apply"):
        await pause_shadow_book(
            PauseShadowBookOperatorRequest(
                tenant="bullsofdhaka",
                handle="analyst",
                portfolio_id=uuid.uuid4(),
                reason="Historical diagnostic failed its registered evidence gates.",
            )
        )


@pytest.mark.asyncio
async def test_operator_refuses_a_strategy_from_another_tenant_market() -> None:
    with pytest.raises(RuntimeError, match="registered for US, not DSE"):
        await configure_lifecycle(
            LifecycleOperatorRequest(
                tenant="bullsofdhaka",
                handle="analyst",
                strategy_key="us_breakout_v1",
                initial_capital=10_000_000,
                apply=True,
            )
        )


@pytest.mark.asyncio
async def test_replay_operator_requires_explicit_apply_acknowledgement() -> None:
    with pytest.raises(RuntimeError, match="without --apply"):
        await seed_historical_replay(
            HistoricalReplayOperatorRequest(
                tenant="bullsofwallst",
                handle="analyst",
                strategy_key="us_breakout_v1",
                initial_capital=100_000,
            )
        )


@pytest.mark.asyncio
async def test_replay_operator_refuses_cross_market_strategy() -> None:
    with pytest.raises(RuntimeError, match="registered for DSE, not US"):
        await seed_historical_replay(
            HistoricalReplayOperatorRequest(
                tenant="bullsofwallst",
                handle="analyst",
                strategy_key="dse_reversal_v1",
                initial_capital=100_000,
                apply=True,
            )
        )
