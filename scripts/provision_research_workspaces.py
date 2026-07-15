"""Backfill private Atlas workspaces for existing interactive accounts.

New and previously missed accounts are also covered by the API's idempotent first-use provisioning.
This command exists to make an open-access rollout observable before users first visit Atlas.
Automated official desks are excluded by default; pass ``--include-official`` only deliberately.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from pathlib import Path
from typing import Literal

from sqlalchemy import select

from api.institutional_research.workspaces import (
    bootstrap_personal_workspace,
    list_accessible_workspaces,
)
from api.research_access import bind_research_tenant_context
from bulls.core.db import bind_tenant_context, dispose_engine, get_sessionmaker
from bulls.core.models import User
from bulls.core.tenancy import Tenant, TenantRegistry

_REPOSITORY = Path(__file__).resolve().parents[1]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit workspace provisioning; the default is a read-only dry run.",
    )
    parser.add_argument(
        "--include-official",
        action="store_true",
        help="Also provision official desk/agent accounts.",
    )
    return parser.parse_args()


async def _eligible_user_ids(tenant: Tenant, *, include_official: bool) -> list[int]:
    async with get_sessionmaker()() as session:
        await bind_tenant_context(session, tenant.name)
        statement = select(User.id).where(User.tenant_id == tenant.name)
        if not include_official:
            statement = statement.where(User.is_official.is_(False))
        return list((await session.scalars(statement.order_by(User.id))).all())


ProvisioningStatus = Literal["existing", "missing", "created"]


async def _workspace_status(
    tenant: Tenant,
    user_id: int,
    *,
    apply: bool,
) -> ProvisioningStatus:
    async with get_sessionmaker()() as session:
        await bind_tenant_context(session, tenant.name)
        user = await session.get(User, user_id)
        if user is None or user.tenant_id != tenant.name:
            raise RuntimeError(f"User {user_id} is outside tenant {tenant.name}")
        await bind_research_tenant_context(
            session,
            tenant_id=tenant.name,
            market=tenant.market,
            user_id=user.id,
        )
        existing = await list_accessible_workspaces(session, tenant=tenant, user_id=user.id)
        if existing:
            return "existing"
        if not apply:
            return "missing"
        await bootstrap_personal_workspace(session, tenant=tenant, user=user)
        await session.commit()
        return "created"


async def run(*, apply: bool, include_official: bool) -> None:
    registry = TenantRegistry.from_dir(_REPOSITORY / "tenants", default="bullsofdhaka")
    try:
        for tenant in registry.all():
            if tenant.research_access != "authenticated":
                print(f"{tenant.name}: skipped (research access is closed)")
                continue
            user_ids = await _eligible_user_ids(tenant, include_official=include_official)
            counts: Counter[str] = Counter()
            for user_id in user_ids:
                counts[await _workspace_status(tenant, user_id, apply=apply)] += 1
            mode = "apply" if apply else "dry run"
            print(
                f"{tenant.name}: {len(user_ids)} eligible accounts; "
                f"{counts['existing']} existing, {counts['created']} created, "
                f"{counts['missing']} missing ({mode})"
            )
    finally:
        await dispose_engine()


if __name__ == "__main__":
    options = _arguments()
    asyncio.run(run(apply=options.apply, include_official=options.include_official))
