"""Low-cost discovery inputs for the private US onboarding universe.

SEC frames provide a recent shares-outstanding estimate for broad discovery. Yahoo's batch spark
endpoint provides EOD closes; bounded per-symbol chart requests provide liquidity observations only
for cap-qualified candidates. These are discovery inputs only: full per-issuer EDGAR and price-history
gates remain mandatory before a symbol can be promoted.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import statistics
from collections.abc import Iterable, Mapping
from typing import Any

import httpx
from pydantic import BaseModel

from bulls.market_data.providers.us_yahoo import YAHOO_CHART_URL, parse_yahoo_chart, yahoo_symbol

SEC_SHARES_FRAME_URL = (
    "https://data.sec.gov/api/xbrl/frames/dei/"
    "EntityCommonStockSharesOutstanding/shares/{period}.json"
)
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
YAHOO_SPARK_URL = "https://query1.finance.yahoo.com/v7/finance/spark"
_SHARES_CONCEPTS = (
    ("dei", "EntityCommonStockSharesOutstanding"),
    ("us-gaap", "CommonStockSharesOutstanding"),
)


class SharesObservation(BaseModel):
    cik: int
    shares: float
    end: dt.date
    accession: str
    period: str


class PriceLiquidityObservation(BaseModel):
    symbol: str
    price_as_of: dt.date
    latest_close: float
    sessions: int
    median_dollar_volume_mn_20d: float | None = None
    nonzero_volume_ratio: float | None = None


def parse_sec_shares_frame(data: Mapping[str, Any], *, period: str) -> dict[int, SharesObservation]:
    """Return one positive shares observation per CIK from an official SEC frame."""
    observations: dict[int, SharesObservation] = {}
    rows = data.get("data")
    if not isinstance(rows, list):
        return observations
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        try:
            cik = int(row["cik"])
            shares = float(row["val"])
            end = dt.date.fromisoformat(str(row["end"]))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if cik <= 0 or not 0 < shares < 1e14:
            continue
        candidate = SharesObservation(
            cik=cik,
            shares=shares,
            end=end,
            accession=str(row.get("accn") or ""),
            period=period,
        )
        current = observations.get(cik)
        if current is None or (candidate.end, candidate.accession) > (
            current.end,
            current.accession,
        ):
            observations[cik] = candidate
    return observations


def merge_share_frames(
    frames: Iterable[Mapping[int, SharesObservation]],
) -> dict[int, SharesObservation]:
    """Prefer the most recent observation when a filer appears in several quarter frames."""
    merged: dict[int, SharesObservation] = {}
    for frame in frames:
        for cik, candidate in frame.items():
            current = merged.get(cik)
            if current is None or (candidate.end, candidate.accession) > (
                current.end,
                current.accession,
            ):
                merged[cik] = candidate
    return merged


def parse_sec_company_facts_shares(data: Mapping[str, Any]) -> SharesObservation | None:
    """Extract the latest positive common-share observation from a Company Facts payload."""
    try:
        cik = int(data["cik"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    facts = data.get("facts")
    if cik <= 0 or not isinstance(facts, Mapping):
        return None

    candidates: list[tuple[dt.date, dt.date, str, float, str]] = []
    for taxonomy, concept in _SHARES_CONCEPTS:
        taxonomy_facts = facts.get(taxonomy)
        concept_data = taxonomy_facts.get(concept) if isinstance(taxonomy_facts, Mapping) else None
        units = concept_data.get("units") if isinstance(concept_data, Mapping) else None
        rows = units.get("shares") if isinstance(units, Mapping) else None
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            try:
                end = dt.date.fromisoformat(str(row["end"]))
                filed = dt.date.fromisoformat(str(row.get("filed") or row["end"]))
                shares = float(row["val"])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if not 0 < shares < 1e14:
                continue
            candidates.append(
                (
                    end,
                    filed,
                    str(row.get("accn") or ""),
                    shares,
                    str(row.get("frame") or "companyfacts"),
                )
            )
    if not candidates:
        return None
    end, _, accession, shares, period = max(candidates, key=lambda row: row[:3])
    return SharesObservation(
        cik=cik,
        shares=shares,
        end=end,
        accession=accession,
        period=period,
    )


def _valid_session_rows(response: Mapping[str, Any]) -> list[tuple[int, float, int | None]]:
    timestamps = response.get("timestamp")
    indicators = response.get("indicators")
    if not isinstance(timestamps, list) or not isinstance(indicators, Mapping):
        return []
    quote_sets = indicators.get("quote")
    if not isinstance(quote_sets, list) or not quote_sets or not isinstance(quote_sets[0], Mapping):
        return []
    closes = quote_sets[0].get("close")
    volumes = quote_sets[0].get("volume")
    if not isinstance(closes, list):
        return []
    if not isinstance(volumes, list):
        volumes = [None] * len(closes)

    rows: list[tuple[int, float, int | None]] = []
    for timestamp, close, volume in zip(timestamps, closes, volumes, strict=False):
        try:
            timestamp_i = int(timestamp)
            close_f = float(close)
        except (TypeError, ValueError, OverflowError):
            continue
        try:
            volume_i = int(volume) if volume is not None else None
        except (TypeError, ValueError, OverflowError):
            volume_i = None
        if timestamp_i <= 0 or close_f <= 0 or (volume_i is not None and volume_i < 0):
            continue
        rows.append((timestamp_i, close_f, volume_i))
    return rows


def parse_yahoo_spark(data: Mapping[str, Any]) -> dict[str, PriceLiquidityObservation]:
    spark = data.get("spark")
    results = spark.get("result") if isinstance(spark, Mapping) else None
    if not isinstance(results, list):
        return {}

    observations: dict[str, PriceLiquidityObservation] = {}
    for result in results:
        if not isinstance(result, Mapping):
            continue
        symbol = str(result.get("symbol") or "").strip().upper()
        responses = result.get("response")
        if not symbol or not isinstance(responses, list) or not responses:
            continue
        response = responses[0]
        if not isinstance(response, Mapping):
            continue
        rows = _valid_session_rows(response)
        if not rows:
            continue
        recent = rows[-20:]
        dollar_volumes = [
            close * volume / 1e6 for _, close, volume in recent if volume is not None
        ]
        volumes = [volume for _, _, volume in rows if volume is not None]
        timestamp, close, _ = rows[-1]
        observations[symbol] = PriceLiquidityObservation(
            symbol=symbol,
            price_as_of=dt.datetime.fromtimestamp(timestamp, tz=dt.UTC).date(),
            latest_close=round(close, 6),
            sessions=len(rows),
            median_dollar_volume_mn_20d=(
                round(statistics.median(dollar_volumes), 6) if dollar_volumes else None
            ),
            nonzero_volume_ratio=(
                round(sum(volume > 0 for volume in volumes) / len(volumes), 6)
                if volumes
                else None
            ),
        )
    return observations


async def _get_json_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str] | None = None,
    missing_ok: bool = False,
) -> dict[str, Any]:
    for attempt in range(4):
        response = await client.get(url, params=params)
        if response.status_code == 404 and missing_ok:
            return {}
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == 3:
                response.raise_for_status()
            await asyncio.sleep(2**attempt)
            continue
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    return {}


async def fetch_sec_share_frames(
    periods: Iterable[str], *, user_agent: str
) -> dict[int, SharesObservation]:
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    frames: list[dict[int, SharesObservation]] = []
    async with httpx.AsyncClient(headers=headers, timeout=60.0, follow_redirects=True) as client:
        for period in periods:
            payload = await _get_json_with_retry(
                client,
                SEC_SHARES_FRAME_URL.format(period=period),
                missing_ok=True,
            )
            if payload:
                frames.append(parse_sec_shares_frame(payload, period=period))
            await asyncio.sleep(0.25)
    return merge_share_frames(frames)


async def fetch_sec_company_facts_shares(
    ciks: Iterable[int],
    *,
    user_agent: str,
    requests_per_second: float = 5.0,
) -> dict[int, SharesObservation]:
    """Resolve frame gaps through bounded official Company Facts requests."""
    if requests_per_second <= 0 or requests_per_second > 8:
        raise ValueError("requests_per_second must be within (0, 8]")
    selected = sorted({int(cik) for cik in ciks if int(cik) > 0})
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    observations: dict[int, SharesObservation] = {}
    async with httpx.AsyncClient(headers=headers, timeout=60.0, follow_redirects=True) as client:
        for cik in selected:
            payload = await _get_json_with_retry(
                client,
                SEC_COMPANY_FACTS_URL.format(cik=cik),
                missing_ok=True,
            )
            observation = parse_sec_company_facts_shares(payload)
            if observation is not None and observation.cik == cik:
                observations[cik] = observation
            await asyncio.sleep(1 / requests_per_second)
    return observations


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


async def fetch_yahoo_spark(
    symbols: Iterable[str],
    *,
    batch_size: int = 20,
    concurrency: int = 3,
) -> dict[str, PriceLiquidityObservation]:
    """Fetch recent EOD closes in bounded Yahoo batches."""
    codes = sorted({str(code).strip().upper() for code in symbols if str(code).strip()})
    semaphore = asyncio.Semaphore(concurrency)
    headers = {
        "User-Agent": "Mozilla/5.0 BullsOfTheWorld/0.1 us-universe-discovery",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(headers=headers, timeout=45.0, follow_redirects=True) as client:
        async def fetch(batch: list[str]) -> dict[str, PriceLiquidityObservation]:
            try:
                async with semaphore:
                    requested_by_yahoo = {code.replace(".", "-"): code for code in batch}
                    symbols_query = ",".join(requested_by_yahoo)
                    payload = await _get_json_with_retry(
                        client,
                        f"{YAHOO_SPARK_URL}?symbols={symbols_query}&range=3mo&interval=1d",
                    )
            except httpx.HTTPStatusError as error:
                if error.response.status_code not in {400, 404}:
                    raise
                if len(batch) == 1:
                    return {}
                midpoint = len(batch) // 2
                left, right = await asyncio.gather(fetch(batch[:midpoint]), fetch(batch[midpoint:]))
                return {**left, **right}
            parsed = parse_yahoo_spark(payload)
            mapped = {
                requested_by_yahoo.get(code, code): observation.model_copy(
                    update={"symbol": requested_by_yahoo.get(code, code)}
                )
                for code, observation in parsed.items()
            }
            missing = [code for code in batch if code not in mapped]
            if not missing:
                return mapped
            if len(batch) == 1:
                return mapped
            if len(missing) == len(batch):
                midpoint = len(batch) // 2
                left, right = await asyncio.gather(fetch(batch[:midpoint]), fetch(batch[midpoint:]))
                return {**left, **right}
            return {**mapped, **(await fetch(missing))}

        results = await asyncio.gather(*(fetch(batch) for batch in _chunks(codes, batch_size)))
    return {code: observation for result in results for code, observation in result.items()}


async def fetch_yahoo_chart_liquidity(
    symbols: Iterable[str], *, concurrency: int = 8
) -> dict[str, PriceLiquidityObservation]:
    """Fetch full three-month price/volume histories only for cap-preselected candidates."""
    codes = sorted({str(code).strip().upper() for code in symbols if str(code).strip()})
    semaphore = asyncio.Semaphore(concurrency)
    headers = {
        "User-Agent": "Mozilla/5.0 BullsOfTheWorld/0.1 us-universe-discovery",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(headers=headers, timeout=45.0, follow_redirects=True) as client:
        async def fetch(code: str) -> tuple[str, PriceLiquidityObservation | None]:
            async with semaphore:
                try:
                    payload = await _get_json_with_retry(
                        client,
                        YAHOO_CHART_URL.format(symbol=yahoo_symbol(code)),
                        params={
                            "range": "3mo",
                            "interval": "1d",
                            "events": "history",
                            "includeAdjustedClose": "true",
                        },
                        missing_ok=True,
                    )
                except httpx.HTTPStatusError as error:
                    if error.response.status_code == 400:
                        return code, None
                    raise
            bars = parse_yahoo_chart(payload, market="US", code=code)
            if not bars:
                return code, None
            recent = bars[-20:]
            dollar_volumes = [bar.close * bar.volume / 1e6 for bar in recent]
            return code, PriceLiquidityObservation(
                symbol=code,
                price_as_of=bars[-1].date,
                latest_close=round(bars[-1].close, 6),
                sessions=len(bars),
                median_dollar_volume_mn_20d=round(statistics.median(dollar_volumes), 6),
                nonzero_volume_ratio=round(sum(bar.volume > 0 for bar in bars) / len(bars), 6),
            )

        results = await asyncio.gather(*(fetch(code) for code in codes))
    return {code: observation for code, observation in results if observation is not None}
