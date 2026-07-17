"""Generate deterministic private-research cohorts for every active US product listing.

This catalog is intentionally broader than the cap-band discovery universe. It includes common
stocks, ADRs, and ETFs, but assigns instrument-specific evidence requirements so an ETF is never
failed for lacking issuer Company Facts. Generation is read-only; cohort execution remains the
durable, gated ``universe_onboarding`` workflow.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import select

from bulls.core.db import get_sessionmaker
from bulls.core.models import SecurityMaster
from ingestion.lineage import content_sha256

MARKET = "US"
SCHEMA_VERSION = 1
DEFAULT_COHORT_SIZE = 100
INSTRUMENT_ORDER = ("common_stock", "adr", "etf")


def _policy(instrument_type: str) -> dict[str, Any]:
    common = {
        "allowed_instrument_types": [instrument_type],
        "min_bars": 252,
        "min_history_days": 365,
        "max_staleness_days": 10,
        "min_adjusted_close_ratio": 0.98,
        "min_nonzero_volume_ratio": 0.80,
        "min_sec_filings": 1,
        "min_sec_facts": 1,
        "require_analytics": True,
        "require_13f": False,
        "min_market_cap_mn": None,
        "max_market_cap_mn": None,
        "min_adtv_mn": None,
        "min_price": None,
        "requires_risk_review": False,
    }
    if instrument_type == "common_stock":
        return {
            **common,
            "require_cik_for": ["common_stock"],
            "sec_filings_required_for": ["common_stock"],
            "sec_facts_required_for": ["common_stock"],
        }
    if instrument_type == "adr":
        return {
            **common,
            "require_cik_for": ["adr"],
            "sec_filings_required_for": ["adr"],
            "sec_facts_required_for": [],
        }
    if instrument_type == "etf":
        return {
            **common,
            "require_cik_for": [],
            "sec_filings_required_for": [],
            "sec_facts_required_for": [],
            "min_sec_filings": 0,
            "min_sec_facts": 0,
        }
    raise ValueError(f"unsupported instrument type: {instrument_type}")


def catalog_payloads(
    records: list[tuple[str, str]],
    *,
    snapshot_date: dt.date,
    cohort_size: int = DEFAULT_COHORT_SIZE,
) -> tuple[list[tuple[str, dict[str, Any]]], dict[str, Any]]:
    """Return cohort files and an index from ``(symbol, instrument_type)`` records."""
    if cohort_size < 1 or cohort_size > 500:
        raise ValueError("cohort_size must be between 1 and 500")
    grouped: dict[str, list[str]] = defaultdict(list)
    for raw_symbol, instrument_type in records:
        symbol = raw_symbol.strip().upper()
        if instrument_type not in INSTRUMENT_ORDER:
            continue
        grouped[instrument_type].append(symbol)

    files: list[tuple[str, dict[str, Any]]] = []
    index_rows: list[dict[str, Any]] = []
    for instrument_type in INSTRUMENT_ORDER:
        symbols = sorted(set(grouped[instrument_type]))
        for offset in range(0, len(symbols), cohort_size):
            cohort_symbols = symbols[offset : offset + cohort_size]
            ordinal = offset // cohort_size + 1
            stem = f"full-{instrument_type.replace('_', '-')}-{ordinal:03d}"
            filename = f"{stem}.json"
            payload = {
                "schema_version": SCHEMA_VERSION,
                "name": stem,
                "version": snapshot_date.isoformat(),
                "market": MARKET,
                "backfill_years": 10,
                "description": (
                    f"Private Atlas foundation coverage for active US {instrument_type} listings; "
                    "public publication remains separately licensed and gated."
                ),
                "risk_review_id": None,
                "allow_restricted_research": False,
                "symbols": cohort_symbols,
                "policy": _policy(instrument_type),
            }
            digest = content_sha256(payload)
            files.append((filename, payload))
            index_rows.append(
                {
                    "band": instrument_type,
                    "instrument_type": instrument_type,
                    "file": filename,
                    "symbols": len(cohort_symbols),
                    "first_symbol": cohort_symbols[0],
                    "last_symbol": cohort_symbols[-1],
                    "manifest_sha256": digest,
                }
            )
    index = {
        "schema_version": SCHEMA_VERSION,
        "market": MARKET,
        "snapshot_date": snapshot_date.isoformat(),
        "cohort_size": cohort_size,
        "symbols": sum(row["symbols"] for row in index_rows),
        "cohorts": index_rows,
    }
    return files, index


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(rendered)
    temporary.replace(path)


async def generate(output_dir: Path, *, cohort_size: int) -> dict[str, Any]:
    sm = get_sessionmaker()
    async with sm() as session:
        records = list(
            (
                await session.execute(
                    select(SecurityMaster.symbol, SecurityMaster.instrument_type)
                    .where(
                        SecurityMaster.market == MARKET,
                        SecurityMaster.is_active.is_(True),
                        SecurityMaster.is_product_eligible.is_(True),
                    )
                    .order_by(SecurityMaster.instrument_type, SecurityMaster.symbol)
                )
            ).all()
        )
    files, index = catalog_payloads(
        [(symbol, instrument_type) for symbol, instrument_type in records],
        snapshot_date=dt.datetime.now(dt.UTC).date(),
        cohort_size=cohort_size,
    )
    for filename, payload in files:
        _atomic_write(output_dir / filename, payload)
    _atomic_write(output_dir / "manifest-index.json", index)
    return {**index, "output_dir": str(output_dir)}


def _parse_args() -> argparse.Namespace:
    today = dt.datetime.now(dt.UTC).date().isoformat()
    parser = argparse.ArgumentParser(description="Generate the complete private US research catalog")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("var/us-full-universe") / today,
    )
    parser.add_argument("--cohort-size", type=int, default=DEFAULT_COHORT_SIZE)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = asyncio.run(generate(args.output_dir, cohort_size=args.cohort_size))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
