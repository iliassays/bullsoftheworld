"""Calendar / seasonality study on DSE — the turn-of-month and day-of-week effects.

Institutions exploit calendar flows (salary/fund inflows cluster at month turns). These anomalies are
well-documented in emerging markets. Tests them on the DSEX index (no shorting / no new data needed):
is the index's return concentrated in the turn-of-month window? Are some weekdays reliably better?
A timing overlay, not a stock picker — could gate when Scheme-3 enters, or time index exposure.

    uv run python scripts/seasonality.py
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

from sqlalchemy import select

from bulls.core.db import get_sessionmaker
from bulls.core.models import MarketSummary

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


async def _run():
    sm = get_sessionmaker()
    async with sm() as s:
        rows = list(await s.scalars(select(MarketSummary).where(MarketSummary.market == "DSE")))
    series = sorted(((r.date, r.dsex) for r in rows if r.dsex), key=lambda x: x[0])

    # group trading days by calendar month to mark turn-of-month positions
    by_month = defaultdict(list)
    for d, _ in series:
        by_month[(d.year, d.month)].append(d)
    pos_from_start, pos_from_end = {}, {}
    for days in by_month.values():
        for i, d in enumerate(days):
            pos_from_start[d] = i + 1
            pos_from_end[d] = len(days) - i

    tom, rest, dow = [], [], defaultdict(list)
    for k in range(1, len(series)):
        d, px = series[k]
        prev = series[k - 1][1]
        if not prev:
            continue
        ret = (px / prev - 1) * 100
        dow[d.weekday()].append(ret)
        # turn-of-month = last trading day of a month OR first 3 of the next
        if pos_from_end[d] == 1 or pos_from_start[d] <= 3:
            tom.append(ret)
        else:
            rest.append(ret)

    def stat(xs):
        m = sum(xs) / len(xs)
        hit = sum(1 for x in xs if x > 0) / len(xs) * 100
        return m, hit, len(xs)

    print("DSEX daily return by calendar window (avg % per day, % of days positive):\n")
    for label, xs in (("TURN-OF-MONTH (last 1 + first 3)", tom), ("rest of month", rest)):
        m, hit, n = stat(xs)
        print(f"  {label:<34}{m:>+7.3f}%/day   {hit:>4.0f}% up   n={n}")
    # how much of the total index move happened in each bucket
    tot_tom = sum(tom)
    tot_rest = sum(rest)
    print(f"\n  Summed return: turn-of-month {tot_tom:+.1f}%  vs  rest-of-month {tot_rest:+.1f}%")
    print(
        f"  (turn-of-month is ~{len(tom)} days vs ~{len(rest)} days — most of the year is 'rest')"
    )

    print("\nDSEX daily return by weekday (DSE trades Sun-Thu):")
    for wd in (6, 0, 1, 2, 3):  # Sun, Mon, Tue, Wed, Thu
        if dow[wd]:
            m, hit, n = stat(dow[wd])
            print(f"  {DOW[wd]:<5}{m:>+7.3f}%/day   {hit:>4.0f}% up   n={n}")


if __name__ == "__main__":
    asyncio.run(_run())
