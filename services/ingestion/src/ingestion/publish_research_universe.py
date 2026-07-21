"""Owner-acknowledged research publication of already-evaluated US symbols.

Staging deliberately never publishes: ``universe_onboarding_batch`` runs every generated cohort
with ``promote=False``, so symbols that clear every gate stay private until someone decides to
open them. This command performs that decision for evidence already on record.

What it does and does not claim:

- It applies the **same** publication policy the cohort path uses
  (``research_publication_status``) to the latest recorded evaluation per symbol. No gate is
  re-interpreted, no provider fetch is repeated, and a symbol that failed a hard gate stays
  private exactly as before.
- It requires an explicit ``--risk-review-id``: the owner acknowledgement that publication was
  considered and accepted. That identifier is written into an immutable run record.
- It does **not** assert a market-data redistribution contract. That is a different, stricter
  gate (``US_MARKET_DATA_AUTHORIZATION_ID`` with the cohort ``--promote`` path) and this command
  deliberately cannot satisfy it on the owner's behalf.

Usage::

    python -m ingestion.publish_research_universe --risk-review-id <id> --dry-run
    python -m ingestion.publish_research_universe --risk-review-id <id>
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import sys
from typing import Any

from sqlalchemy import func, select, update

from bulls.core.db import get_sessionmaker
from bulls.core.models import Symbol, UniverseOnboardingResult, UniverseOnboardingRun
from bulls.core.symbol_lifecycle import research_publication_status

PUBLICATION_COHORT_NAME = "owner-research-publication"


async def _latest_evidence(session, market: str) -> list[UniverseOnboardingResult]:
    """Latest recorded evaluation per symbol — a symbol re-run many times counts once."""
    newest = (
        select(
            UniverseOnboardingResult.code.label("code"),
            func.max(UniverseOnboardingResult.evaluated_at).label("evaluated_at"),
        )
        .where(UniverseOnboardingResult.market == market)
        .group_by(UniverseOnboardingResult.code)
        .subquery()
    )
    rows = await session.scalars(
        select(UniverseOnboardingResult).join(
            newest,
            (UniverseOnboardingResult.code == newest.c.code)
            & (UniverseOnboardingResult.evaluated_at == newest.c.evaluated_at),
        ).where(UniverseOnboardingResult.market == market)
    )
    # Guard against two evaluations sharing a timestamp for one code.
    unique: dict[str, UniverseOnboardingResult] = {}
    for row in rows:
        unique[row.code] = row
    return list(unique.values())


def plan_publication(
    evidence: list[UniverseOnboardingResult],
) -> dict[str, list[str]]:
    """Map recorded evidence to target publication tiers. Pure function."""
    planned: dict[str, list[str]] = {"ready": [], "research_only": []}
    for row in evidence:
        status = research_publication_status(
            row.required_gates_passed, list(row.failure_reasons or [])
        )
        if status is not None:
            planned[status].append(row.code)
    return planned


async def publish(*, market: str, risk_review_id: str, dry_run: bool) -> dict[str, Any]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        evidence = await _latest_evidence(session, market)
        planned = plan_publication(evidence)
        summary: dict[str, Any] = {
            "market": market,
            "risk_review_id": risk_review_id,
            "evaluated_symbols": len(evidence),
            "planned": {status: len(codes) for status, codes in planned.items()},
            "published": {},
            "dry_run": dry_run,
        }
        if dry_run:
            return summary

        now = dt.datetime.now(dt.UTC)
        published_total = 0
        for status, codes in planned.items():
            if not codes:
                summary["published"][status] = 0
                continue
            result = await session.execute(
                update(Symbol)
                .where(
                    Symbol.market == market,
                    Symbol.code.in_(codes),
                    Symbol.is_active.is_(True),
                    Symbol.data_status != status,
                )
                .values(data_status=status, is_hidden=False)
            )
            count = int(result.rowcount or 0)
            summary["published"][status] = count
            published_total += count

        # Immutable audit record: what was opened, on whose acknowledgement, and under which policy.
        parameters = {
            "risk_review_id": risk_review_id,
            "policy": "research_publication_status",
            "market_data_authorization_asserted": False,
            "planned": {status: len(codes) for status, codes in planned.items()},
            "published": summary["published"],
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                {"market": market, "risk_review_id": risk_review_id, "at": now.isoformat()},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        session.add(
            UniverseOnboardingRun(
                market=market,
                cohort_name=PUBLICATION_COHORT_NAME,
                cohort_version=now.date().isoformat(),
                manifest_sha256=fingerprint,
                status="completed",
                promotion_requested=True,
                requested_count=len(evidence),
                passed_count=published_total,
                failed_count=0,
                parameters=parameters,
                completed_at=now,
            )
        )
        await session.commit()
        summary["audit_fingerprint"] = fingerprint
        return summary


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", default="US")
    parser.add_argument(
        "--risk-review-id",
        required=True,
        help="owner acknowledgement identifier recorded in the audit trail",
    )
    parser.add_argument("--dry-run", action="store_true", help="report counts without publishing")
    return parser.parse_args(argv)


def main() -> None:
    args = _args()
    if not args.risk_review_id.strip():
        raise SystemExit("--risk-review-id must not be blank")
    summary = asyncio.run(
        publish(
            market=args.market,
            risk_review_id=args.risk_review_id.strip(),
            dry_run=args.dry_run,
        )
    )
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
