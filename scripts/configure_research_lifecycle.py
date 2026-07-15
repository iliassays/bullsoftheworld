"""Configure and optionally dispatch one Atlas lifecycle for one explicit account.

This is an operator command, not a tenant scanner. It binds PostgreSQL row security to the
requested tenant, market, and user before reading or writing research state.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from api.institutional_research.operator import (
    LifecycleOperatorRequest,
    configure_lifecycle,
)
from bulls.analytics.research_strategy import STRATEGIES
from bulls.core.db import dispose_engine

_CAP_TIERS = ("mega", "large", "mid", "small", "micro", "penny")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True, help="Exact configured tenant name.")
    parser.add_argument("--handle", required=True, help="Exact account handle within the tenant.")
    parser.add_argument("--strategy-key", required=True, choices=sorted(STRATEGIES))
    parser.add_argument("--initial-capital", required=True, type=float)
    parser.add_argument("--queue-limit", type=int, default=20)
    parser.add_argument("--research-limit", type=int, default=5)
    parser.add_argument("--universe-limit", type=int, default=25)
    parser.add_argument("--cap-tier", choices=_CAP_TIERS)
    parser.add_argument("--enable", action="store_true", help="Enable recurring post-close runs.")
    parser.add_argument(
        "--dispatch-now",
        action="store_true",
        help="Also enqueue one immediate lifecycle without changing its recurrence semantics.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Required acknowledgement before any database or queue mutation.",
    )
    return parser.parse_args()


async def _main(options: argparse.Namespace) -> None:
    try:
        result = await configure_lifecycle(
            LifecycleOperatorRequest(
                tenant=options.tenant,
                handle=options.handle,
                strategy_key=options.strategy_key,
                initial_capital=options.initial_capital,
                queue_limit=options.queue_limit,
                research_limit=options.research_limit,
                universe_limit=options.universe_limit,
                cap_tier=options.cap_tier,
                enable=options.enable,
                dispatch_now=options.dispatch_now,
                apply=options.apply,
            )
        )
        print(json.dumps(result, indent=2, sort_keys=True))
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main(_arguments()))
