"""Seed the five agent model-portfolio users (৳1,00,000 each). Idempotent: re-running only
creates what's missing — it NEVER resets cash, holdings, or trade history of an existing agent
(that history is the whole point of the experiment; wipe it only by hand, deliberately).

    uv run python scripts/seed_agent_portfolios.py

The users are created with portfolio_public=false: the portfolios are reviewed from the admin
cockpit only. Making them publicly visible is a product/regulatory decision (advice-adjacent),
not a default — flip the flag consciously if that day comes.
"""

from __future__ import annotations

import asyncio
import secrets

from sqlalchemy import select

from bulls.analytics import STRATEGIES
from bulls.core.db import get_sessionmaker
from bulls.core.models import AgentPortfolio, User
from bulls.core.security import hash_password

TENANT = "bullsofdhaka"
MARKET = "DSE"
INITIAL_CAPITAL = 100_000.0  # ৳1 lac per portfolio


async def main() -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        created = 0
        for spec in STRATEGIES.values():
            user = (
                await session.scalars(
                    select(User).where(User.tenant_id == TENANT, User.handle == spec.handle)
                )
            ).one_or_none()
            if user is None:
                user = User(
                    tenant_id=TENANT,
                    handle=spec.handle,
                    name=spec.display_name,
                    locale="en",
                    # Nobody logs in as an agent — a random throwaway password, never printed.
                    password_hash=hash_password(secrets.token_urlsafe(24)),
                    is_official=True,  # same badge as the desk accounts: clearly the platform's own
                    portfolio_public=False,
                )
                session.add(user)
                await session.flush()
            account = await session.get(AgentPortfolio, user.id)
            if account is None:
                session.add(
                    AgentPortfolio(
                        user_id=user.id,
                        market=MARKET,
                        strategy=spec.key,
                        initial_capital=INITIAL_CAPITAL,
                        cash_settled=INITIAL_CAPITAL,
                    )
                )
                created += 1
                print(f"created @{spec.handle} ({spec.key}) with ৳{INITIAL_CAPITAL:,.0f}")
            else:
                print(f"@{spec.handle} already exists — left untouched")
        await session.commit()
        print(f"done: {created} new agent portfolios")


if __name__ == "__main__":
    asyncio.run(main())
