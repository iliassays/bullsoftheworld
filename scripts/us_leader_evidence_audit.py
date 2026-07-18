"""Audit normalized SEC fact CSV input through the point-in-time leader adapter.

The script reads CSV from stdin by default. It is intentionally database-agnostic so production
data can be inspected through a read-only export without copying a database or changing state.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from typing import TextIO

from bulls.analytics.leader_capture import LeaderFinancialFact, build_leader_evidence


def _input(path: str) -> TextIO:
    return sys.stdin if path == "-" else Path(path).open(encoding="utf-8", newline="")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", nargs="?", default="-")
    args = parser.parse_args()
    handle = _input(args.csv_path)
    try:
        facts = [
            LeaderFinancialFact(
                code=row["code"],
                metric=row["metric"],
                value=float(row["value"]),
                period_start=row["period_start"] or None,
                period_end=row["period_end"],
                period_type=row["period_type"],
                form=row["form"],
                accession_number=row["accession_number"],
                source_url=row["source_url"],
                known_at=dt.datetime.fromisoformat(row["known_at"]),
                normalization_version=row["normalization_version"],
            )
            for row in csv.DictReader(handle)
        ]
    finally:
        if handle is not sys.stdin:
            handle.close()

    evidence = build_leader_evidence(facts)
    summary = {
        code: {
            "observations": len(observations),
            "first_known_at": (observations[0].known_at.isoformat() if observations else None),
            "latest_known_at": (observations[-1].known_at.isoformat() if observations else None),
            "latest_effective_date": (
                observations[-1].effective_date.isoformat() if observations else None
            ),
            "latest_features": observations[-1].features if observations else {},
        }
        for code, observations in sorted(evidence.items())
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
