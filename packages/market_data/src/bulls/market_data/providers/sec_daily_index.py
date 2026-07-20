"""EDGAR daily-index client: the market-wide filing event stream.

Unlike ``sec_edgar.SecEdgarClient`` (per-company submissions for issuers we already track),
this client answers "what was filed *today*, by anyone" — the input the filings-event
research (institutional study, Phase 14 Stage 0.1) needs for 13D/G and Form 4 streams.

Two design rules carried over from the study's validation protocol:

- Every fetch returns the raw bytes untouched so the caller can archive them
  content-addressed; replay from the archive must be byte-identical to the live fetch.
- The index for a weekend/holiday simply does not exist upstream; that is an empty
  day, not an error. The poller runs unattended and must not page anyone for Saturdays.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re
import time

import httpx
from pydantic import BaseModel

_BASE = "https://www.sec.gov/Archives"

# Filename tail like 0001067983-26-000045.txt -> the accession number.
_ACCESSION_RE = re.compile(r"(\d{10}-\d{2}-\d{6})\.txt$")


class DailyIndexEntry(BaseModel):
    """One row of an EDGAR master daily index."""

    cik: int
    company: str
    form: str
    date_filed: dt.date
    filename: str

    @property
    def accession_number(self) -> str | None:
        return accession_from_filename(self.filename)


def accession_from_filename(filename: str) -> str | None:
    match = _ACCESSION_RE.search(filename)
    return match.group(1) if match else None


def parse_master_index(text: str, *, forms: set[str] | None = None) -> list[DailyIndexEntry]:
    """Parse a ``master.<date>.idx`` file into entries, optionally filtered by form type.

    Malformed rows are skipped, never raised: the poller runs unattended and one bad
    row must not block the day's other filings.
    """
    entries: list[DailyIndexEntry] = []
    in_body = False
    for line in text.splitlines():
        if not in_body:
            # The body starts after the dashed separator that follows the column header.
            if line.startswith("----"):
                in_body = True
            continue
        parts = line.split("|")
        if len(parts) != 5:
            continue
        raw_cik, company, form, raw_date, filename = (part.strip() for part in parts)
        if forms is not None and form not in forms:
            continue
        try:
            entries.append(
                DailyIndexEntry(
                    cik=int(raw_cik),
                    company=company,
                    form=form,
                    date_filed=dt.date.fromisoformat(raw_date),
                    filename=filename,
                )
            )
        except (ValueError, TypeError):
            continue
    return entries


class SecDailyIndexClient:
    """Small respectful client for daily indexes and raw filing documents.

    Mirrors ``SecEdgarClient``'s conventions: mandatory identifying User-Agent per SEC
    policy, injectable transport for tests, and sleep-based throttling well below the
    SEC's 10 req/s ceiling.
    """

    def __init__(
        self,
        user_agent: str,
        *,
        requests_per_second: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not user_agent.strip() or "@" not in user_agent:
            raise ValueError(
                "SEC User-Agent must identify the product and a monitored contact email"
            )
        self._headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        }
        self._interval = 1 / requests_per_second
        self._last_request = 0.0
        self._transport = transport

    def index_path(self, day: dt.date) -> str:
        quarter = (day.month - 1) // 3 + 1
        return (
            f"{_BASE}/edgar/daily-index/{day.year}/QTR{quarter}/"
            f"master.{day:%Y%m%d}.idx"
        )

    async def fetch_day(
        self, day: dt.date, *, forms: set[str] | None = None
    ) -> tuple[bytes | None, list[DailyIndexEntry]]:
        """Fetch one day's master index. Returns (raw bytes, parsed entries).

        A 404 means no index exists for that day (weekend/holiday): returns (None, []).
        """
        raw = await self._get_bytes(self.index_path(day), allow_not_found=True)
        if raw is None:
            return None, []
        return raw, parse_master_index(raw.decode("latin-1"), forms=forms)

    async def fetch_filing(self, filename: str) -> bytes | None:
        """Fetch a raw filing document by its index ``filename`` path, byte-exact."""
        return await self._get_bytes(f"{_BASE}/{filename}", allow_not_found=True)

    async def _get_bytes(self, url: str, *, allow_not_found: bool = False) -> bytes | None:
        async with httpx.AsyncClient(
            headers=self._headers, timeout=30.0, transport=self._transport
        ) as client:
            for attempt in range(4):
                delay = self._interval - (time.monotonic() - self._last_request)
                if delay > 0:
                    await asyncio.sleep(delay)
                self._last_request = time.monotonic()
                response = await client.get(url)
                if allow_not_found and response.status_code == 404:
                    return None
                if response.status_code not in {429, 500, 502, 503, 504}:
                    response.raise_for_status()
                    return response.content
                await asyncio.sleep(2**attempt)
            response.raise_for_status()
            raise AssertionError("unreachable")
