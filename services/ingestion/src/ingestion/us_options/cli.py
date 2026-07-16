"""Operator CLI for licensed US-options Phase A imports.

Example:
    uv run python -m ingestion.us_options.cli import-sentiment \
      /secure/inbox/HighLevelOptionSentiment_Complete_2026-07-15.zip \
      --known-at 2026-07-16T10:00:00Z \
      --revision final-2026-07-15
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
from pathlib import Path

from bulls.core.db import get_sessionmaker
from ingestion.us_options.evaluation import (
    render_feasibility_markdown,
    run_option_sentiment_feasibility,
)
from ingestion.us_options.pipeline import import_option_sentiment


def _timestamp(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed


async def _import(args: argparse.Namespace) -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        snapshot = await import_option_sentiment(
            session,
            path=args.path,
            known_at=args.known_at,
            completeness=args.completeness,
            source_revision=args.revision,
            delivery_mode=args.delivery_mode,
        )
        await session.commit()
    print(
        f"snapshot={snapshot.id} date={snapshot.trade_date} status={snapshot.status} "
        f"rows={snapshot.row_count} raw={snapshot.raw_sha256}"
    )


def _delivery_files(directory: str) -> list[Path]:
    root = Path(directory).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("historical import path must be a directory")
    files = sorted(
        path
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in {".csv", ".zip"}
    )
    if not files:
        raise ValueError("historical import directory contains no CSV or ZIP deliveries")
    return files


async def _import_directory(args: argparse.Namespace) -> None:
    files = _delivery_files(args.directory)
    sm = get_sessionmaker()
    accepted = rejected = failed = 0
    for number, path in enumerate(files, start=1):
        try:
            async with sm() as session:
                snapshot = await import_option_sentiment(
                    session,
                    path=path,
                    known_at=args.known_at,
                    completeness="complete",
                    source_revision=args.revision,
                    delivery_mode="historical",
                )
                await session.commit()
            if snapshot.status == "accepted":
                accepted += 1
            else:
                rejected += 1
            print(
                f"[{number}/{len(files)}] {path.name}: {snapshot.status} "
                f"date={snapshot.trade_date} rows={snapshot.row_count}"
            )
        except Exception as exc:
            failed += 1
            print(f"[{number}/{len(files)}] {path.name}: failed: {exc}")
    print(
        f"historical_import files={len(files)} accepted={accepted} "
        f"rejected={rejected} failed={failed}"
    )
    if failed or rejected:
        raise SystemExit(1)


async def _evaluate(args: argparse.Namespace) -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        evaluation, report = await run_option_sentiment_feasibility(
            session,
            start_date=args.start,
            end_date=args.end,
        )
        await session.commit()
    print(render_feasibility_markdown(report))
    print(
        f"evaluation={evaluation.id} report={evaluation.report_object_key} "
        f"sha256={evaluation.report_sha256}"
    )


def _date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _add_import_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--known-at", required=True, type=_timestamp)
    parser.add_argument("--revision", required=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Licensed US-options research ingestion")
    commands = parser.add_subparsers(dest="command", required=True)
    sentiment = commands.add_parser("import-sentiment")
    sentiment.add_argument("path")
    _add_import_options(sentiment)
    sentiment.add_argument(
        "--completeness",
        choices=("preliminary", "complete", "sample"),
        default="complete",
    )
    sentiment.add_argument(
        "--delivery-mode",
        choices=("historical", "subscription"),
        default="historical",
    )
    historical = commands.add_parser(
        "import-sentiment-directory",
        help="resumable sequential import of a historical Cboe order",
    )
    historical.add_argument("directory")
    _add_import_options(historical)
    evaluate = commands.add_parser(
        "evaluate-sentiment",
        help="persist the registered descriptive feasibility report",
    )
    evaluate.add_argument("--start", required=True, type=_date)
    evaluate.add_argument("--end", required=True, type=_date)
    args = parser.parse_args()
    if args.command == "import-sentiment":
        asyncio.run(_import(args))
    elif args.command == "import-sentiment-directory":
        asyncio.run(_import_directory(args))
    elif args.command == "evaluate-sentiment":
        asyncio.run(_evaluate(args))


if __name__ == "__main__":
    main()
