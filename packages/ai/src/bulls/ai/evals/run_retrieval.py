"""Run the DB-backed retrieval regression set.

Requires the target embedding model to be indexed in Postgres:

    uv run python -m bulls.ai.evals.run_retrieval
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from bulls.ai.retrieval import retrieve
from bulls.core.db import get_sessionmaker

CASES = Path(__file__).resolve().parents[4] / "evals" / "retrieval_cases.json"


async def run() -> int:
    cases = json.loads(CASES.read_text())
    passed = 0
    reciprocal_rank = 0.0
    sm = get_sessionmaker()
    async with sm() as session:
        for case in cases:
            chunks = await retrieve(
                session,
                case["query"],
                market=case["market"],
                tenant_id=case["tenant_id"],
                code=case["code"],
                k=6,
            )
            expected = set(case["expected_source_types"])
            rank = next(
                (index for index, chunk in enumerate(chunks, start=1) if chunk.source_type in expected),
                None,
            )
            max_rank = int(case.get("max_rank", 3))
            ok = rank is not None and rank <= max_rank
            passed += int(ok)
            reciprocal_rank += 1 / rank if rank is not None else 0
            print(
                f"{'PASS' if ok else 'FAIL'} {case['id']}: "
                f"expected one of {sorted(expected)} by rank {max_rank}, "
                f"rank={rank or 'missing'}, returned={[chunk.source_type for chunk in chunks]}"
            )
    mrr = reciprocal_rank / len(cases) if cases else 0.0
    print(f"retrieval top-rank pass rate: {passed}/{len(cases)}; MRR={mrr:.3f}")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
