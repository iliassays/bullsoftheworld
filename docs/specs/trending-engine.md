# Trending engine — "Active today" (আজকের সক্রিয়)

Status: **Phase 1 built & live** (staging + prod), June 2026. Backtested before building.

## What it is
A daily ranking of stocks whose trading activity is **unusual for themselves** — "what's worth
watching today." It replaces the meaning of the old top-gainers strip (which just showed the same
illiquid circuit small-caps every day). Precomputed nightly (heavy); the frontend reads a plain list.

## Why this design (the backtest decided it)
We backtested candidate signals on 2 years of `daily_bars` (walk-forward, strict no-lookahead) —
`scripts/trending_backtest.py`. Findings (out-of-sample):

| Signal | rank-IC | precision@10 |
|---|---|---|
| Turnover surge (vs own normal) | +0.40 | 54% |
| Volume surge | +0.40 | 54% |
| Abnormal move (σ-adjusted) | +0.17 | 39% |
| Range expansion | +0.19 | 34% |
| Breakout (52w/20d) | +0.13 | 27% |
| Persistence/momentum | +0.05 | ~23% (≈ noise) |
| **Composite (vol+turnover)** | **+0.40** | **~54%** |
| Current top-gainers strip (baseline) | — | 33.5% |
| Random (base rate) | — | 16.3% |

**Conclusion:** the only real edge is self-normalized **volume + turnover surge**. The lean model
beats the full composite. So the rank = `vol_z + turnover_z`; everything else (move, breakout, 52w)
is shown as a **descriptive chip**, never a rank driver. Label = "abnormal forward turnover and/or
abnormal forward move over the next 5 days."

## How it's computed
`services/ingestion/src/ingestion/trending.py :: compute_trending(market)`
- For each stock: `vol_z` and `to_z` = log-space z-score of today vs the trailing 60 days (excl today),
  recomputed from `daily_bars` (note: `ticker_analytics` is a snapshot, no history — can't be used).
- Score = `vol_z + to_z`. Direction-agnostic (a surge counts whether price rose or fell).
- `heating_up` = both z ≥ 2.
- `reasons` = language-neutral chip data (volume mult, turnover ৳cr + mult, near 52w high/low,
  move %, limit up/down). The frontend renders the human text per locale.
- Writes the top 25 to `trending_scores` (replaces the prior set each run).

## Regulatory posture (do not weaken without thought)
Descriptive activity, **never advice** — and we must not become a pump megaphone (BSEC sensitivity,
thin market). Guardrails, all enforced in `compute_trending`:
- **Public universe gated hard:** median-20d turnover ≥ ৳50 lakh, market cap ≥ ৳50 cr, **Z-category
  excluded** — only names too liquid for our audience to move.
- **Balanced up/down** (direction-agnostic score), not a one-sided "what's going up" hype board.
- **Pull-only** (in-app list); **no push notifications**. EOD/lagged, not intraday "buy now".
- Footer: "past activity, not a prediction." No buyout/squeeze/sentiment speculation.
- The user wants a **BD securities lawyer / BSEC read before any scaled push or Facebook broadcast.**

## Surfaces
- API: `GET /trending-stocks` (`services/api/src/api/routers/market.py`) — plain ordered read.
- Web: `apps/web/src/components/WatchToday.tsx` on the home Feed; i18n keys `watch.*`.

## Timing (EOD — depends on the day's bars landing first)
Worker crons (UTC, trading days): `pull_eod_bars` 13:00 → `refresh_analytics` 13:15 →
**`run_trending` 13:25**. So the list refreshes ~19:25 Dhaka; during the session it shows the prior
close. The watchdog (see below) alerts if the day's bars/trending don't land by ~20:00 Dhaka.

## Roadmap / open threads
- **Grounded "why it's active" narrative** (the tasteful, fact-locked version of Stocktwits' blurb):
  synthesize a 1–2 sentence story from the anomaly facts + decoded announcements + material crowd —
  no speculation. Discussed, not built. LLM-grounded (cached daily) or deterministic.
- **Phase 2:** Facebook trending card/auto-post — *pending the legal read above*.
- **Phase 3:** blend social signals (watcher growth, post/reaction velocity) once the user base is
  big enough; then "আলোচিত" (discussed) becomes an honest label.
- **Optional:** an intraday overlay (live volume vs normal) — the validated engine is EOD-only.

## Ops / recovery (if a nightly run is missed)
The EOD chain can be re-run by hand (idempotent), in order:
`ingestion.history daily` → `ingestion.analytics` → `ingestion.trending` → agent runners
(`run_levels_agent`, `run_factor_agents`) → `POST /admin/fb/publish-feed` + `/admin/fb/publish`
(kind=evening_wrap). **Do not redeploy during the session or the 13:00–13:50 UTC EOD window** —
heavy restart churn can hang the arq cron loop (the 2026-06-29 incident).
