"""Form 4 insider-purchase event construction for Family I.

Research-only. Builds the (code, signal_date) event sets for I1-I4 from the production Form 4
extract, in polars, so the 191k-row panel version runs in seconds. The semantics deliberately
mirror ``bulls.analytics.fintel_insider_algo``; ``run_insider.py`` asserts agreement against that
production module on a sample of issuers so the two cannot silently drift apart.

Three decisions that determine whether the events mean anything:

**1. Events are stamped with ``known_at``, never ``transaction_date``.** A Form 4 is due two
business days after the trade (verified in this extract: median lag exactly 2 days). Stamping the
transaction date would place the signal in a window where nobody could have filed, let alone
traded, on it.

**2. Routine classification is point-in-time at annual granularity.** An owner counts as
calendar-routine in year ``Y`` only if a same-calendar-month purchase run of three consecutive
years completed strictly *before* ``Y``. Using the full history would leak future trading
patterns into a past classification, which would make the opportunistic set look cleaner than it
could have been known to be.

**3. The signal date is snapped forward to the next trading session.** Filings land at
21:00 UTC and on weekends. The first session at or after the filing is the signal session, and
the harness fills at the session *after* that one — so a late-Friday filing is never treated as
tradeable at Friday's open.
"""

from __future__ import annotations

import datetime as dt
import functools
from pathlib import Path

import polars as pl

from .dataset import DATA_DIR

# EDGAR carries a literal "NONE" trading symbol on filings whose issuer has no listed ticker.
_NULL_SYMBOLS = ("NONE", "N/A", "NA", "")

WINDOW_DAYS = 90
ROUTINE_YEARS = 3


@functools.cache
def purchases() -> pl.DataFrame:
    """Open-market Form 4 purchases with point-in-time acceptance timestamps.

    The extract query already applied: code P, acquired, shares>0, a non-null symbol, and the
    transaction-date plausibility bounds (year >= 1990 and not after the filing that reports it)
    that the production repair migration enforces.
    """
    path = DATA_DIR / "us_form4_purchases.csv"
    frame = pl.read_csv(path, try_parse_dates=True)
    # Postgres COPY CSV writes booleans as t/f.
    flags = ("is_officer", "is_director", "is_ten_percent_owner", "is_10b5_1_plan")
    return (
        frame.with_columns(
            *[(pl.col(flag) == "t").alias(flag) for flag in flags],
            code=pl.col("issuer_symbol").str.to_uppercase().str.strip_chars(),
            known_date=pl.col("known_at").dt.date(),
        )
        .filter(~pl.col("code").is_in(_NULL_SYMBOLS))
        # The published effect is an officer/director effect; bare 10% holders are excluded.
        .filter(pl.col("is_officer") | pl.col("is_director"))
        .drop_nulls(["code", "known_date", "owner_cik"])
    )


def routine_owner_years(frame: pl.DataFrame) -> pl.DataFrame:
    """``(owner_cik, year, is_routine)`` — Cohen-Malloy-Pomorski, resolved point-in-time.

    An owner is routine in year ``Y`` if some calendar month holds purchases in three
    consecutive years whose last year is strictly below ``Y``. Once a programme is established it
    is treated as persisting, which is the conservative direction: it removes buyers from the
    opportunistic set rather than adding them.
    """
    months = (
        frame.select(
            "owner_cik",
            month=pl.col("transaction_date").dt.month(),
            year=pl.col("transaction_date").dt.year(),
        )
        .unique()
        .drop_nulls()
    )
    # A run of three consecutive years in the same month exists iff year, year+1 and year+2 are
    # all present for that (owner, month).
    runs = (
        months.join(months.with_columns(year=pl.col("year") - 1), on=["owner_cik", "month", "year"])
        .join(months.with_columns(year=pl.col("year") - 2), on=["owner_cik", "month", "year"])
        .select("owner_cik", run_end=pl.col("year") + 2)
        .unique()
    )
    if runs.is_empty():
        return pl.DataFrame(
            schema={"owner_cik": pl.Int64, "year": pl.Int32, "is_routine": pl.Boolean}
        )
    first_run = runs.group_by("owner_cik").agg(first_run_end=pl.col("run_end").min())
    years = pl.DataFrame({"year": list(range(2000, 2031))}, schema={"year": pl.Int32})
    return (
        first_run.join(years, how="cross")
        .with_columns(is_routine=pl.col("year") > pl.col("first_run_end"))
        .filter(pl.col("is_routine"))
        .select("owner_cik", "year", "is_routine")
    )


def _distinct_buyers_in_window(frame: pl.DataFrame, window_days: int) -> pl.DataFrame:
    """Per (code, known_date): distinct owners filing in the trailing ``window_days``.

    Self-join on code rather than a rolling group_by, because the window is in calendar days
    while the rows are irregular events.
    """
    dates = frame.select("code", "known_date").unique()
    joined = dates.join(
        frame.select("code", "owner_cik", buy_date="known_date"), on="code", how="inner"
    ).filter(
        (pl.col("buy_date") <= pl.col("known_date"))
        & (pl.col("buy_date") > pl.col("known_date") - dt.timedelta(days=window_days))
    )
    return joined.group_by("code", "known_date").agg(
        buyers=pl.col("owner_cik").n_unique(),
        buys=pl.len(),
    )


def build_events(window_days: int = WINDOW_DAYS) -> dict[str, pl.DataFrame]:
    """The four Family I event sets, keyed by spec key.

    I1/I2 partition the opportunistic (non-plan, non-routine) set by breadth. I3 and I4 are the
    registered nulls: scheduled and calendar-routine purchases, which must not predict.
    """
    frame = purchases()
    routine = routine_owner_years(frame)
    tagged = (
        frame.with_columns(year=pl.col("known_date").dt.year().cast(pl.Int32))
        .join(routine, on=["owner_cik", "year"], how="left")
        .with_columns(is_routine=pl.col("is_routine").fill_null(False))
    )

    opportunistic = tagged.filter(~pl.col("is_10b5_1_plan") & ~pl.col("is_routine"))
    scheduled = tagged.filter(pl.col("is_10b5_1_plan"))
    routine_buys = tagged.filter(~pl.col("is_10b5_1_plan") & pl.col("is_routine"))

    opp_counts = _distinct_buyers_in_window(opportunistic, window_days)
    return {
        "us_insider_cluster_buy": opp_counts.filter(pl.col("buyers") >= 2),
        "us_insider_single_buy": opp_counts.filter(pl.col("buyers") == 1),
        "us_insider_plan_buy_null": _distinct_buyers_in_window(scheduled, window_days),
        "us_insider_routine_buy_null": _distinct_buyers_in_window(routine_buys, window_days),
    }


def snap_to_sessions(events: pl.DataFrame, sessions: pl.Series) -> pl.DataFrame:
    """Map each filing date to the first trading session at or after it.

    Events whose filing postdates the last session in the panel are dropped — there is no
    session on which they could have been observed.
    """
    calendar = pl.DataFrame({"date": sessions.unique().sort()}).with_columns(
        known_date=pl.col("date")
    )
    return (
        events.sort("known_date")
        .join_asof(
            calendar.sort("known_date"),
            on="known_date",
            strategy="forward",
        )
        .drop_nulls("date")
    )


def attach_to_panel(panel: pl.DataFrame, events: pl.DataFrame) -> pl.DataFrame:
    """Inner-join events onto the eligible, control-attached panel on (code, session)."""
    snapped = snap_to_sessions(events, panel["date"])
    return panel.join(
        snapped.select("code", "date", "buyers", "buys").unique(subset=["code", "date"]),
        on=["code", "date"],
        how="inner",
    )


def coverage_report() -> dict:
    """Facts a reader needs before believing any Family I number."""
    frame = purchases()
    return {
        "purchase_rows": frame.height,
        "issuers": frame["issuer_cik"].n_unique(),
        "codes": frame["code"].n_unique(),
        "known_date_min": str(frame["known_date"].min()),
        "known_date_max": str(frame["known_date"].max()),
        "transaction_date_min": str(frame["transaction_date"].min()),
        "median_filing_lag_days": float(
            frame.select(
                (pl.col("known_date") - pl.col("transaction_date")).dt.total_days().median()
            ).item()
        ),
        "plan_rows": int(frame.select(pl.col("is_10b5_1_plan").sum()).item()),
        "extract": str(Path(DATA_DIR / "us_form4_purchases.csv").name),
    }
