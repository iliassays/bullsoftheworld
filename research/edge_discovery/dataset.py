"""Local read-only panel built from the production extract.

Research-only. Nothing here writes to production, and nothing here is imported by the API,
the ingestion service, or any Atlas agent. The extract is a point-in-time *copy* pulled on
2026-07-25; every experiment in this package reads that copy so results are reproducible
without re-querying production.

Two hard rules encoded here rather than left to the experiments:

1. ``forward_returns`` never looks at a bar the signal date could not have seen. Entry is the
   session *after* the signal session, always.
2. The US panel carries an explicit ``survivorship`` flag. Every US code in the store has a bar
   in the final week (verified 2026-07-25: 11,072 of 11,072), so the US panel is a survivors-only
   sample and any experiment reading it must treat a positive result as an upper bound.
"""

from __future__ import annotations

import datetime as dt
import functools
import gzip
import shutil
from dataclasses import dataclass
from pathlib import Path

import polars as pl

DATA_DIR = Path(
    "/private/tmp/claude-501/-Users-iliashossain-project-millionare-bulls-of-the-world"
    "/f8d6f3a8-9d5b-4636-ac60-804fe70fad22/scratchpad/data"
)
EXTRACT_DATE = dt.date(2026, 7, 25)


@dataclass(frozen=True)
class PanelMeta:
    """What the experiments must know about the panel they were handed."""

    market: str
    price_basis: str
    survivorship: str
    first_session: dt.date
    last_session: dt.date
    sessions: int
    codes: int


def _ensure_parquet(csv_name: str, parquet_name: str, gzipped: bool = False) -> Path:
    """Convert an extract CSV to parquet once; later calls reuse it."""
    parquet = DATA_DIR / parquet_name
    if parquet.exists():
        return parquet
    source = DATA_DIR / csv_name
    if gzipped:
        plain = DATA_DIR / csv_name.removesuffix(".gz")
        if not plain.exists():
            with gzip.open(source, "rb") as fh, plain.open("wb") as out:
                shutil.copyfileobj(fh, out)
        source = plain
    pl.scan_csv(source, try_parse_dates=True).sink_parquet(parquet)
    return parquet


@functools.cache
def us_bars() -> pl.DataFrame:
    """US common-stock and ADR daily bars, split/distribution adjusted.

    ``adjusted_close`` is retroactively restated by the vendor, so a price *level* filter
    (for example "close < $1") sees post-hoc split-adjusted levels rather than the level that
    actually traded. Returns are unaffected; level filters must use raw ``close``.
    """
    path = _ensure_parquet("us_bars.csv.gz", "us_bars.parquet", gzipped=True)
    frame = pl.read_parquet(path)
    return frame.sort(["code", "date"])


@functools.cache
def dse_bars() -> pl.DataFrame:
    """DSE daily bars. Raw closes only — production holds zero adjusted closes for DSE."""
    path = _ensure_parquet("dse_bars.csv", "dse_bars.parquet")
    return pl.read_parquet(path).sort(["code", "date"])


@functools.cache
def benchmarks() -> pl.DataFrame:
    path = _ensure_parquet("us_bench.csv", "us_bench.parquet")
    return pl.read_parquet(path).sort(["code", "date"])


@functools.cache
def dsex() -> pl.DataFrame:
    path = _ensure_parquet("dsex.csv", "dsex.parquet")
    return pl.read_parquet(path).sort("date")


@functools.cache
def dse_announcements() -> pl.DataFrame:
    path = _ensure_parquet("dse_ann.csv", "dse_ann.parquet")
    return pl.read_parquet(path)


@functools.cache
def short_interest() -> pl.DataFrame:
    """FINRA consolidated short interest, gated on ``known_at`` (settlement + ~8 trading days).

    Verified 2026-07-25: eight settlement dates, 2026-03-31 to 2026-07-15. This is a forward
    collection, not a history.
    """
    path = _ensure_parquet("short_interest.csv", "short_interest.parquet")
    return pl.read_parquet(path)


@functools.cache
def security_master() -> pl.DataFrame:
    path = _ensure_parquet("us_secmaster.csv", "us_secmaster.parquet")
    return pl.read_parquet(path)


def panel_meta(market: str) -> PanelMeta:
    frame = us_bars() if market == "US" else dse_bars()
    survivorship = (
        "total — every code in the store trades in the final week; no delisted histories"
        if market == "US"
        else "near-total — 397 of 401 codes trade in the final year"
    )
    return PanelMeta(
        market=market,
        price_basis="adjusted_close (retroactively restated)"
        if market == "US"
        else "raw close — NO corporate-action adjustment",
        survivorship=survivorship,
        first_session=frame["date"].min(),
        last_session=frame["date"].max(),
        sessions=frame["date"].n_unique(),
        codes=frame["code"].n_unique(),
    )


def with_features(bars: pl.DataFrame, price_col: str = "adjusted_close") -> pl.DataFrame:
    """Attach the standard per-code feature set.

    Every feature is computed from bars at or before the row's own session, so a row is safe to
    use as a signal observation. Forward-looking columns are added separately by
    :func:`forward_returns` and are named with a ``fwd_`` prefix so they can never be mistaken
    for inputs.
    """
    price = pl.col(price_col)
    ret = (price / price.shift(1) - 1).over("code")
    turnover = pl.col("close") * pl.col("volume")

    return bars.with_columns(
        ret=ret,
        sma_20=price.rolling_mean(20).over("code"),
        sma_50=price.rolling_mean(50).over("code"),
        sma_200=price.rolling_mean(200).over("code"),
        vol_20=ret.rolling_std(20).over("code"),
        vol_60=ret.rolling_std(60).over("code"),
        adv_20=turnover.rolling_mean(20).over("code"),
        avg_vol_20=pl.col("volume").rolling_mean(20).over("code"),
        high_20=pl.col("high").rolling_max(20).over("code"),
        low_20=pl.col("low").rolling_min(20).over("code"),
        high_52w=pl.col("high").rolling_max(252).over("code"),
        low_52w=pl.col("low").rolling_min(252).over("code"),
        ret_5=(price / price.shift(5) - 1).over("code"),
        ret_21=(price / price.shift(21) - 1).over("code"),
        ret_63=(price / price.shift(63) - 1).over("code"),
        ret_126=(price / price.shift(126) - 1).over("code"),
        ret_252=(price / price.shift(252) - 1).over("code"),
        # 12-1 momentum: the standard construction skips the most recent month to avoid the
        # short-term reversal effect contaminating the momentum measurement.
        mom_12_1=(price.shift(21) / price.shift(252) - 1).over("code"),
        bars_seen=pl.int_range(pl.len()).over("code"),
    )


def add_atr(frame: pl.DataFrame, window: int = 14) -> pl.DataFrame:
    """True-range based ATR. Uses only current and prior bars."""
    prev_close = pl.col("close").shift(1).over("code")
    true_range = pl.max_horizontal(
        pl.col("high") - pl.col("low"),
        (pl.col("high") - prev_close).abs(),
        (pl.col("low") - prev_close).abs(),
    )
    return frame.with_columns(true_range=true_range).with_columns(
        atr=pl.col("true_range").rolling_mean(window).over("code")
    )


def forward_returns(
    bars: pl.DataFrame, horizons: tuple[int, ...], price_col: str = "adjusted_close"
) -> pl.DataFrame:
    """Attach forward returns measured from the NEXT session's open.

    A signal observed at the close of session ``t`` can only be acted on at session ``t+1``.
    ``fwd_h`` is therefore ``close[t+h] / open[t+1] - 1`` — no same-bar execution anywhere.
    ``fwd_entry`` is the modelled entry price before costs.
    """
    entry = pl.col("open").shift(-1).over("code")
    # Open is unadjusted in the store while closes are adjusted; rescale the open onto the
    # adjusted scale using the same session's close ratio so entry and exit share one basis.
    if price_col == "adjusted_close":
        scale = pl.col("adjusted_close") / pl.col("close")
        entry = (pl.col("open") * scale).shift(-1).over("code")

    frame = bars.with_columns(fwd_entry=entry)
    columns = []
    for horizon in horizons:
        exit_price = pl.col(price_col).shift(-horizon).over("code")
        columns.append((exit_price / pl.col("fwd_entry") - 1).alias(f"fwd_{horizon}"))
        columns.append(
            (pl.col("high").shift(-horizon).over("code") * 0 + exit_price).alias(
                f"fwd_exit_{horizon}"
            )
        )
    return frame.with_columns(columns)
