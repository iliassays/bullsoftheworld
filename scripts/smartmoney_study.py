"""Smart-money flow study (DSE) — does rising institutional/foreign ownership predict returns?

For each disclosed ownership change, lags entry to when the filing would actually be public
(~15 trading days after month-end), then measures the forward return. Groups by flow to see whether
"smart money accumulating" names go on to outperform. INDICATIVE only: ownership history is thin
(~3 snapshots/name) and disclosure dates cluster, so the usable sample is small. This is a first read,
to be re-run as the weekly scrape accumulates monthly history.

    uv run python scripts/smartmoney_study.py
"""

from __future__ import annotations

import asyncio
import itertools as it
import statistics as st

from sqlalchemy import select

from bulls.core.db import get_sessionmaker
from bulls.core.models import DailyBar, ShareholdingSnapshot

LAG = 15  # trading days after the as-of date before the holding is realistically public
FWD = 30  # forward trading-day horizon to measure


async def _run():
    sm = get_sessionmaker()
    async with sm() as s:
        snaps = list(
            await s.scalars(
                select(ShareholdingSnapshot)
                .where(ShareholdingSnapshot.market == "DSE")
                .order_by(ShareholdingSnapshot.code, ShareholdingSnapshot.as_of_date)
            )
        )
        bars = list(
            await s.scalars(
                select(DailyBar)
                .where(DailyBar.market == "DSE")
                .order_by(DailyBar.code, DailyBar.date)
            )
        )

    by_code: dict[str, list] = {}
    for b in bars:
        by_code.setdefault(b.code, []).append(b)
    snap_by: dict[str, list] = {}
    for sn in snaps:
        snap_by.setdefault(sn.code, []).append(sn)

    obs = []  # (net_flow, inst_flow, fwd_return)
    for code, sl in snap_by.items():
        cl = by_code.get(code)
        if not cl or len(sl) < 2:
            continue
        dates = [b.date for b in cl]
        for prev, cur in it.pairwise(sl):
            inst = (cur.institute or 0) - (prev.institute or 0)
            fgn = (cur.foreign_pct or 0) - (prev.foreign_pct or 0)
            # entry = first bar on/after as_of + LAG trading days; forward FWD bars
            import bisect

            i = bisect.bisect_left(dates, cur.as_of_date)
            e = i + LAG
            if e + FWD >= len(cl) or e >= len(cl) or not cl[e].close:
                continue
            fwd = (cl[e + FWD].close / cl[e].close - 1) * 100
            obs.append((inst + fgn, inst, fwd))

    print(f"Usable flow observations: {len(obs)}  (lag {LAG}d, forward {FWD}d)\n")
    if len(obs) < 20:
        print(
            "Too few to say anything — need the accumulating monthly history. (Showing what we have.)"
        )
    rets = [o[2] for o in obs]
    base = st.mean(rets)
    print(
        f"Baseline: all flow events avg forward return {base:+.1f}%  (win {sum(1 for r in rets if r > 0) / len(rets) * 100:.0f}%)\n"
    )

    # quintile-ish split by net institutional+foreign flow
    obs.sort(key=lambda o: o[0])
    third = len(obs) // 3
    groups = [
        ("DISTRIBUTING (flow down)", obs[:third]),
        ("flat", obs[third : 2 * third]),
        ("ACCUMULATING (flow up)", obs[2 * third :]),
    ]
    print(f"{'GROUP':<28}{'avg fwd%':>10}{'median':>9}{'win%':>7}{'n':>6}")
    print("-" * 62)
    for name, g in groups:
        gr = [o[2] for o in g]
        print(
            f"{name:<28}{st.mean(gr):>+10.1f}{st.median(gr):>+9.1f}{sum(1 for r in gr if r > 0) / len(gr) * 100:>6.0f}%{len(g):>6}"
        )

    # simple rank correlation (Spearman) of flow vs forward return
    def ranks(xs):
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        r = [0.0] * len(xs)
        for pos, i in enumerate(order):
            r[i] = pos
        return r

    fx, fy = ranks([o[0] for o in obs]), ranks(rets)
    n = len(fx)
    mx, my = sum(fx) / n, sum(fy) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(fx, fy, strict=True))
    vx = sum((a - mx) ** 2 for a in fx) ** 0.5
    vy = sum((b - my) ** 2 for b in fy) ** 0.5
    print(
        f"\nFlow vs forward-return rank correlation (IC): {cov / (vx * vy):+.3f}  (>0 = accumulation predicts gains)"
    )


if __name__ == "__main__":
    asyncio.run(_run())
