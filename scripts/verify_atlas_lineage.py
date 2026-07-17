"""Run one tenant-bound Atlas research lineage smoke test.

The command rolls back by default. Pass ``--commit`` to retain the verified run as an ordinary
Atlas research record::

    uv run python scripts/verify_atlas_lineage.py \
      bullsofdhaka DSE <workspace-uuid> <user-id> BSC --commit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid

from api.institutional_research.workflow import execute_company_research
from api.research_access import bind_research_tenant_context
from bulls.core.db import get_sessionmaker
from bulls.core.models import ResearchWorkspace


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify durable Atlas evidence lineage")
    parser.add_argument("tenant_id")
    parser.add_argument("market", choices=("DSE", "US"))
    parser.add_argument("workspace_id", type=uuid.UUID)
    parser.add_argument("user_id", type=int)
    parser.add_argument("code")
    parser.add_argument("--commit", action="store_true")
    return parser.parse_args()


async def _run(options: argparse.Namespace) -> None:
    async with get_sessionmaker()() as session:
        await bind_research_tenant_context(
            session,
            tenant_id=options.tenant_id,
            market=options.market,
            user_id=options.user_id,
        )
        workspace = await session.get(ResearchWorkspace, options.workspace_id)
        if workspace is None:
            raise RuntimeError("workspace is not visible in the supplied tenant/user boundary")
        if workspace.tenant_id != options.tenant_id or workspace.market != options.market:
            raise RuntimeError("workspace tenant/market does not match the requested boundary")

        run = await execute_company_research(
            session,
            workspace=workspace,
            user_id=options.user_id,
            code=options.code.upper(),
            idempotency_key=f"lineage-smoke-v1:{options.market}:{options.code.upper()}",
        )
        lineage = run.parameters.get("lineage")
        if not isinstance(lineage, dict):
            raise RuntimeError("research run did not record its lineage summary")
        claims_without_citations = [
            claim.ordinal for claim in run.claims if not claim.citations
        ]
        if claims_without_citations:
            raise RuntimeError(
                f"research claims lack durable citations: {claims_without_citations}"
            )
        if not run.claims or int(lineage.get("citation_count", 0)) <= 0:
            raise RuntimeError("research run produced no claim/citation lineage")

        result = {
            "run_id": str(run.id),
            "tenant_id": run.tenant_id,
            "market": run.market,
            "code": run.code,
            "status": run.status,
            "lineage": lineage,
            "claim_citations": {
                str(claim.ordinal): len(claim.citations) for claim in run.claims
            },
            "committed": options.commit,
        }
        if options.commit:
            await session.commit()
        else:
            await session.rollback()
        print(json.dumps(result, indent=2, sort_keys=True))


def main() -> None:
    asyncio.run(_run(_arguments()))


if __name__ == "__main__":
    main()
