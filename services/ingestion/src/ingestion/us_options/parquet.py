"""Deterministic normalized Parquet serialization for options research."""

from __future__ import annotations

import io

import polars as pl

from ingestion.us_options.quality import NormalizedOptionSentimentRow


def option_sentiment_parquet(rows: list[NormalizedOptionSentimentRow]) -> bytes:
    if not rows:
        raise ValueError("cannot write an empty option sentiment dataset")
    frame = pl.DataFrame([row.flat() for row in rows]).sort(
        ["trade_date", "underlying_symbol"]
    )
    output = io.BytesIO()
    frame.write_parquet(
        output,
        compression="zstd",
        statistics=True,
    )
    return output.getvalue()
