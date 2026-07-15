from __future__ import annotations

import pytest

from api.institutional_research.operator import (
    LifecycleOperatorRequest,
    configure_lifecycle,
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
