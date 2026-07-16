"""Strict parser for Cboe DataShop Option Sentiment v1.4.

The vendor file is an underlying-level research dataset, not an option chain and not exact
customer opening/closing activity. Parsing is deliberately fail-closed on schema drift, archive
shape, duplicate underlyings, mixed dates, or broken volume relationships.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import math
import zipfile
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CBOE_OPTION_SENTIMENT_SCHEMA_VERSION = "cboe-option-sentiment-v1.4-0525"
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_CSV_BYTES = 256 * 1024 * 1024
MAX_ROWS = 25_000
MAX_COMPRESSION_RATIO = 250
OptionSentimentCompleteness = Literal["preliminary", "complete", "sample"]

CBOE_OPTION_SENTIMENT_COLUMNS = (
    "trade_date",
    "underlying_symbol",
    "call_volume",
    "put_volume",
    "total_volume",
    "avg_call_volume",
    "avg_put_volume",
    "avg_total_volume",
    "call_trades",
    "put_trades",
    "total_trades",
    "avg_call_size",
    "avg_put_size",
    "underlying_volume",
    "call_premium",
    "put_premium",
    "spot_close",
    "split_adj_close",
    "net_option_delta",
    "oi_calls",
    "oi_puts",
    "call_premium_bought",
    "call_premium_sold",
    "put_premium_bought",
    "put_premium_sold",
    "calls_bought",
    "puts_bought",
    "iv30",
    "hv20",
    "vega_total",
    "cust_volume",
    "firm_volume",
    "mkt_mkr_volume",
    "exch_vol_cboe",
    "exch_vol_c2",
    "exch_vol_edgx",
    "exch_vol_bzx",
    "exch_vol_phlx",
    "exch_vol_nom",
    "exch_vol_bxo",
    "exch_vol_gem",
    "exch_vol_ise",
    "exch_vol_merc",
    "exch_vol_amex",
    "exch_vol_arca",
    "exch_vol_miax",
    "exch_vol_pearl",
    "exch_vol_emld",
    "exch_vol_box",
    "implied_borrow",
    "norm_25d_skew_30",
    "iv90",
    "underlying_security_type",
    "otm_call_oi",
    "otm_put_oi",
    "spot_chg",
    "directional_pct",
    "size1",
    "size2_10",
    "size11_100",
    "size101_500",
    "size501_1000",
    "size1001up",
    "dtx1",
    "dtx2_5",
    "dtx6_30",
    "dtx31_90",
    "dtx91_180",
    "dtx181_360",
    "dtx360up",
    "calls_sold",
    "puts_sold",
    "itmcalls",
    "atmcalls",
    "otmcalls",
    "itmputs",
    "atmputs",
    "otmputs",
    "exch_vol_memx",
    "exch_vol_sphr",
)

_INTEGER_FIELDS = {
    "call_volume",
    "put_volume",
    "total_volume",
    "avg_call_volume",
    "avg_put_volume",
    "avg_total_volume",
    "call_trades",
    "put_trades",
    "total_trades",
    "underlying_volume",
    "oi_calls",
    "oi_puts",
    "calls_bought",
    "puts_bought",
    "vega_total",
    "cust_volume",
    "firm_volume",
    "mkt_mkr_volume",
    "exch_vol_cboe",
    "exch_vol_c2",
    "exch_vol_edgx",
    "exch_vol_bzx",
    "exch_vol_phlx",
    "exch_vol_nom",
    "exch_vol_bxo",
    "exch_vol_gem",
    "exch_vol_ise",
    "exch_vol_merc",
    "exch_vol_amex",
    "exch_vol_arca",
    "exch_vol_miax",
    "exch_vol_pearl",
    "exch_vol_emld",
    "exch_vol_box",
    "otm_call_oi",
    "otm_put_oi",
    "size1",
    "size2_10",
    "size11_100",
    "size101_500",
    "size501_1000",
    "size1001up",
    "dtx1",
    "dtx2_5",
    "dtx6_30",
    "dtx31_90",
    "dtx91_180",
    "dtx181_360",
    "dtx360up",
    "calls_sold",
    "puts_sold",
    "itmcalls",
    "atmcalls",
    "otmcalls",
    "itmputs",
    "atmputs",
    "otmputs",
    "exch_vol_memx",
    "exch_vol_sphr",
}
_FLOAT_FIELDS = set(CBOE_OPTION_SENTIMENT_COLUMNS) - _INTEGER_FIELDS - {
    "trade_date",
    "underlying_symbol",
    "underlying_security_type",
}


class CboeOptionSentimentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trade_date: dt.date
    underlying_symbol: str = Field(min_length=1, max_length=32)
    call_volume: int = Field(ge=0)
    put_volume: int = Field(ge=0)
    total_volume: int = Field(ge=0)
    avg_call_volume: int = Field(ge=0)
    avg_put_volume: int = Field(ge=0)
    avg_total_volume: int = Field(ge=0)
    call_trades: int = Field(ge=0)
    put_trades: int = Field(ge=0)
    total_trades: int = Field(ge=0)
    avg_call_size: float | None = Field(default=None, ge=0)
    avg_put_size: float | None = Field(default=None, ge=0)
    underlying_volume: int = Field(ge=0)
    call_premium: float = Field(ge=0)
    put_premium: float = Field(ge=0)
    spot_close: float = Field(gt=0)
    split_adj_close: float = Field(gt=0)
    net_option_delta: float
    oi_calls: int = Field(ge=0)
    oi_puts: int = Field(ge=0)
    call_premium_bought: float = Field(ge=0)
    call_premium_sold: float = Field(ge=0)
    put_premium_bought: float = Field(ge=0)
    put_premium_sold: float = Field(ge=0)
    calls_bought: int = Field(ge=0)
    puts_bought: int = Field(ge=0)
    iv30: float | None = Field(default=None, ge=0)
    hv20: float | None = Field(default=None, ge=0)
    vega_total: int = Field(ge=0)
    cust_volume: int | None = Field(default=None, ge=0)
    firm_volume: int | None = Field(default=None, ge=0)
    mkt_mkr_volume: int | None = Field(default=None, ge=0)
    exch_vol_cboe: int = Field(ge=0)
    exch_vol_c2: int = Field(ge=0)
    exch_vol_edgx: int = Field(ge=0)
    exch_vol_bzx: int = Field(ge=0)
    exch_vol_phlx: int = Field(ge=0)
    exch_vol_nom: int = Field(ge=0)
    exch_vol_bxo: int = Field(ge=0)
    exch_vol_gem: int = Field(ge=0)
    exch_vol_ise: int = Field(ge=0)
    exch_vol_merc: int = Field(ge=0)
    exch_vol_amex: int = Field(ge=0)
    exch_vol_arca: int = Field(ge=0)
    exch_vol_miax: int = Field(ge=0)
    exch_vol_pearl: int = Field(ge=0)
    exch_vol_emld: int = Field(ge=0)
    exch_vol_box: int = Field(ge=0)
    implied_borrow: float | None = None
    norm_25d_skew_30: float | None = None
    iv90: float | None = Field(default=None, ge=0)
    underlying_security_type: Literal["E", "I", "S"]
    otm_call_oi: int = Field(ge=0)
    otm_put_oi: int = Field(ge=0)
    spot_chg: float
    directional_pct: float = Field(ge=0, le=100)
    size1: int | None = Field(default=None, ge=0)
    size2_10: int | None = Field(default=None, ge=0)
    size11_100: int | None = Field(default=None, ge=0)
    size101_500: int | None = Field(default=None, ge=0)
    size501_1000: int | None = Field(default=None, ge=0)
    size1001up: int | None = Field(default=None, ge=0)
    dtx1: int = Field(ge=0)
    dtx2_5: int = Field(ge=0)
    dtx6_30: int = Field(ge=0)
    dtx31_90: int = Field(ge=0)
    dtx91_180: int = Field(ge=0)
    dtx181_360: int = Field(ge=0)
    dtx360up: int = Field(ge=0)
    calls_sold: int = Field(ge=0)
    puts_sold: int = Field(ge=0)
    itmcalls: int = Field(ge=0)
    atmcalls: int = Field(ge=0)
    otmcalls: int = Field(ge=0)
    itmputs: int = Field(ge=0)
    atmputs: int = Field(ge=0)
    otmputs: int = Field(ge=0)
    exch_vol_memx: int = Field(ge=0)
    exch_vol_sphr: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_aggregates(self) -> CboeOptionSentimentRecord:
        if self.call_volume + self.put_volume != self.total_volume:
            raise ValueError("call_volume + put_volume must equal total_volume")
        if self.call_trades + self.put_trades != self.total_trades:
            raise ValueError("call_trades + put_trades must equal total_trades")
        return self


class CboeOptionSentimentFile(BaseModel):
    schema_version: Literal["cboe-option-sentiment-v1.4-0525"] = (
        CBOE_OPTION_SENTIMENT_SCHEMA_VERSION
    )
    source_filename: str
    completeness: OptionSentimentCompleteness
    known_at: dt.datetime
    trade_date: dt.date
    rows: list[CboeOptionSentimentRecord]


def _date(value: str, *, row_number: int) -> dt.date:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y%m%d"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"invalid trade_date at row {row_number}: {value!r}")


def _number(field: str, value: str, *, row_number: int) -> int | float | None:
    raw = value.strip()
    if not raw:
        return None
    try:
        decimal_value = Decimal(raw)
        if not decimal_value.is_finite():
            raise ValueError
        if field in _INTEGER_FIELDS:
            if decimal_value != decimal_value.to_integral_value():
                raise ValueError
            return int(decimal_value)
        if field in _FLOAT_FIELDS:
            parsed = float(decimal_value)
            if not math.isfinite(parsed):
                raise ValueError
            return parsed
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid {field} at row {row_number}: {value!r}") from exc
    raise AssertionError(f"unregistered numeric field {field}")


def _csv_payload(payload: bytes, *, source_filename: str) -> bytes:
    if payload.startswith(b"PK\x03\x04"):
        if len(payload) > MAX_ARCHIVE_BYTES:
            raise ValueError(f"option sentiment archive exceeds {MAX_ARCHIVE_BYTES} bytes")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            if len(members) != 1:
                raise ValueError("option sentiment archive must contain exactly one CSV file")
            member = members[0]
            if "/" in member.filename or "\\" in member.filename:
                raise ValueError("option sentiment archive member must not contain a path")
            if not member.filename.lower().endswith(".csv"):
                raise ValueError("option sentiment archive member must be a CSV file")
            if member.file_size > MAX_CSV_BYTES:
                raise ValueError(f"option sentiment CSV exceeds {MAX_CSV_BYTES} bytes")
            if (
                member.compress_size > 0
                and member.file_size / member.compress_size > MAX_COMPRESSION_RATIO
            ):
                raise ValueError("option sentiment archive compression ratio is unsafe")
            return archive.read(member)
    if not source_filename.lower().endswith(".csv"):
        raise ValueError("uncompressed option sentiment input must use a .csv filename")
    if len(payload) > MAX_CSV_BYTES:
        raise ValueError(f"option sentiment CSV exceeds {MAX_CSV_BYTES} bytes")
    return payload


def parse_cboe_option_sentiment(
    payload: bytes,
    *,
    source_filename: str,
    completeness: OptionSentimentCompleteness,
    known_at: dt.datetime,
) -> CboeOptionSentimentFile:
    """Parse one complete vendor delivery without inferring unavailable values."""

    if known_at.tzinfo is None or known_at.utcoffset() is None:
        raise ValueError("known_at must be timezone-aware")
    raw_csv = _csv_payload(payload, source_filename=source_filename)
    try:
        text = raw_csv.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("option sentiment CSV must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != CBOE_OPTION_SENTIMENT_COLUMNS:
        raise ValueError("option sentiment schema does not match Cboe v1.4 exactly")

    rows: list[CboeOptionSentimentRecord] = []
    identities: set[tuple[dt.date, str]] = set()
    for row_number, source in enumerate(reader, start=2):
        if len(rows) >= MAX_ROWS:
            raise ValueError(f"option sentiment file exceeds {MAX_ROWS} rows")
        if None in source:
            raise ValueError(f"unexpected extra columns at row {row_number}")
        values: dict[str, object] = {
            "trade_date": _date((source["trade_date"] or "").strip(), row_number=row_number),
            "underlying_symbol": (source["underlying_symbol"] or "").strip(),
            "underlying_security_type": (
                source["underlying_security_type"] or ""
            ).strip().upper(),
        }
        for field in _INTEGER_FIELDS | _FLOAT_FIELDS:
            values[field] = _number(field, source[field] or "", row_number=row_number)
        record = CboeOptionSentimentRecord.model_validate(values)
        identity = (record.trade_date, record.underlying_symbol)
        if identity in identities:
            raise ValueError(
                f"duplicate option sentiment underlying at row {row_number}: "
                f"{record.underlying_symbol}"
            )
        identities.add(identity)
        rows.append(record)

    if not rows:
        raise ValueError("option sentiment file contains no data rows")
    trade_dates = {row.trade_date for row in rows}
    if len(trade_dates) != 1:
        raise ValueError("option sentiment file contains multiple trade dates")
    return CboeOptionSentimentFile(
        source_filename=source_filename,
        completeness=completeness,
        known_at=known_at.astimezone(dt.UTC),
        trade_date=next(iter(trade_dates)),
        rows=rows,
    )
