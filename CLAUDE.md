# Bulls of the World

A multi-tenant social platform for stock markets — think "StockTwits, done local." Users post,
follow, tag stocks with cashtags (`$GP`), set sentiment (bull/bear), and watch market data.

- **Platform:** Bulls of the World (this repo, Python namespace `bulls`)
- **Tenant pattern:** Bulls of `[Market/Place]` → `bullsof[place].com`
- **First tenant:** Bulls of Dhaka — market `DSE`, locale `bn` (Bangla-first)
- **US tenant:** Bulls of Wall Street — market `US`, locale `en`, canonical domain `bullsofwallst.com`

## Core principles (do not violate)

1. **AI is a layer, not the foundation.** Build the social + market-data product first; AI features
   (sentiment, summaries, RAG, fraud detection) sit on top and never block a web request — they run
   in `ai_worker` via the queue. Steps 0–3 of the build have zero AI.
2. **The app never touches a data source directly.** It talks to `MarketDataProvider`
   (`packages/market_data`). Swapping the scraper for a licensed real-time feed = one registry change.
3. **Tenant-agnostic core.** Nothing in `core`/`api` hard-codes DSE or Bangla. A tenant is config
   (market, locale, branding, up/down colors). Resolve the tenant from the request host.
4. **Never fake data freshness.** Every `Quote` carries `is_delayed` + `as_of`; the UI must show it.
5. **Don't gold-plate for traffic we don't have.** Build clean + horizontally scalable, measure, then
   optimize the proven hot path. Real speed comes from Redis byte-caching, CDN, denormalized read
   models — not from the framework or premature distribution.
6. **Right tool, not the trendy tool.** Fraud detection is classic ML, not an LLM. Choose deliberately.
7. **Premium bar.** This product is for retail users but must feel institutional-grade: evidence
   first, clean citations, no lazy chatbot behavior, no stale news framed as today's catalyst, and
   no buy/sell/target output. If a feature can be merely "okay", keep iterating.
8. **RAG contract.** SQL is the source of truth for numbers. pgvector retrieves messy text evidence.
   A movement answer may call something an official catalyst only when the official source is recent;
   older filings are context, not causality. Preferred production retrieval is free local
   `AI_EMBEDDING_PROVIDER=fastembed` with a 768-dim model, then backfill `knowledge_chunks`; `hash`
   is only the dependency-free fallback. Never require Ollama, Claude, or OpenAI for RAG.
9. **Research UX contract.** `Ask this stock` must show the analyst read in the portal: valuation,
   technical, liquidity/flow, ownership, disclosure, and crowd lenses when data exists. Keep it
   descriptive and evidence-backed; never collapse it into unsupported buy/sell language.
10. **Go-to-market contract.** Optimize for weekly activated researchers, not feature count,
    account count or impressions. Retail activation is starting a watchlist (any number of
    stocks — no fixed pick-count target as of 2026-07-15) plus a later research action.
    Institutional enquiries are a separate consented, tenant-scoped funnel. Never market returns.
11. **Atlas investment mandate.** Capital preservation, reproducibility and honest abstention come
    before strategy count or headline returns. The owner prefers strong-trend continuation after a
    controlled micro-pullback, but has delegated strategy adoption to evidence rather than taste.
    Run only a small set of independent, preregistered paper experiments; keep each book, score,
    benchmark and rejection reason separate. A weak or untestable strategy must remain parked.
    Read `docs/research/atlas-investment-mandate.md` before changing Atlas strategies, paper books,
    execution assumptions or promotion gates, and read
    `docs/research/institutional-investment-operating-model.md` before changing its product loop.

## Stack

| Layer | Choice |
|---|---|
| Language / packaging | Python 3.12+ / **uv** workspace |
| Web | **FastAPI** on **Granian** |
| DB | **Postgres + pgvector** (relational + JSON + vector + full-text in one) |
| ORM / migrations | **SQLAlchemy 2.0 async + Alembic** |
| Cache / queue / WS | **Redis** + **arq** |
| AI | Deterministic analytics + free local embeddings (`fastembed`); optional provider-neutral generation, never required for core research |
| Web client | **React + Vite PWA**, Tailwind + shadcn/ui, lightweight-charts (Bangla: Hind Siliguri) |
| Quality | **ruff** + **pytest** |

## Layout

- `packages/core` — `bulls.core`: config, tenancy, db, security, models, schemas
- `packages/market_data` — `bulls.market_data`: provider interface + registry + DSE adapter (the crux)
- `packages/ai` — `bulls.ai`: Claude client, prompts, tasks, retrieval (RAG), evals
- `services/api` — FastAPI: auth, feed, posts, cashtags, WS gateway
- `services/ingestion` — market-data adapters + scheduler
- `services/ai_worker` — async AI jobs
- `apps/web` — React PWA
- `tenants/<name>` — per-tenant config

## Commands

```bash
uv sync                      # install the whole workspace
uv run ruff check . && uv run ruff format .
uv run pytest
docker compose -f infra/docker-compose.yml up -d   # postgres + redis
uv run granian --interface asgi api.main:app --host 0.0.0.0 --port 8000   # run api
```

## Build order

0. ✅ Scaffold + Claude workspace
1. Foundation: models, config, tenancy, health endpoint — no AI
2. **Risky bit:** DSE scraper in `market_data` — prove we can pull clean EOD data
3. Core product: auth, posts, cashtags, symbol pages, feed, watchlists, Bangla UI — no AI
4. First AI feature: sentiment auto-tag + **eval harness**
5. AI depth: embeddings/search → summaries → RAG Q&A → fraud detection → research agent

## Production & operations (Bulls of Dhaka is LIVE)

- **Deploy:** `./deploy.sh` = push → server `git pull` + `uv sync` + `alembic upgrade head` + restart
  `bullsofdhaka-{api,hedge,worker,ai-worker}` (backend, shared by prod+staging). `./deploy-prod.sh`
  (env `PROD_S3_BUCKET=bullsofdhaka-web PROD_CLOUDFRONT_ID=EPJ7LAHUJDDMK`) = build FE → S3 →
  CloudFront invalidate (bullsofdhaka.com). Server access is supplied through
  `DEPLOY_SSH_HOST=<ssh-config-alias>`, app `/home/ubuntu/bullsofdhaka`,
  Postgres in docker (`docker compose -f infra/docker-compose.yml exec -T postgres psql -U bulls -d bulls -p 5432`).
- **US frontend:** `WEB_S3_BUCKET=bullsofwallst-web WEB_CLOUDFRONT_ID=E3DLOEKLM3136G
  WEB_SITE_URL=https://bullsofwallst.com WEB_TENANT_HOST=bullsofwallst.com
  WEB_BRAND_NAME="Bulls of Wall Street" WEB_DEFAULT_LANG=en WEB_API_URL=https://api.bullsofwallst.com
  ./deploy-web.sh` deploys the BullsofWallst static frontend. Distribution:
  `d2jnx1yh0pmbv8.cloudfront.net`; ACM cert:
  `arn:aws:acm:us-east-1:982534375924:certificate/0c63d9f6-5148-45f0-bd2f-ec60ec8a6d31`.
- **Worker rhythm (arq cron, UTC, trading days):** intraday `poll_quotes` {4–8}:{0,15,30,45}; EOD chain
  `pull_eod_bars` 13:00 → `pull_eod_summary` 13:05 → `refresh_analytics` 13:15 → `run_trending` 13:25
  → `run_factor_signals` 13:40 → `run_market_signals` (Evening Wrap → feed+FB) 13:50; `run_morning_watch`
  3:30; `run_weekly_recap` Thu 14:00. arq weekday strings are `mon,tues,wed,thurs,fri,sat,sun`.
- **US SEC worker rhythm (arq cron, UTC, every day — no trading-day gate):**
  `collect_edgar_filing_events` 3:30; `refresh_sec_company_data` 6:15 (**~2h15m**, finishing ~08:30 —
  4,732 symbols measured at 7350s on 2026-08-06, plus ~200 restricted codes and the filing agents;
  it is latency-bound on SEC, not on our 5 req/s throttle); `refresh_sec_institutional_data` Sun
  10:00. This worker sets `retry_jobs=False` + `run_at_startup=False`, so a job killed mid-flight is
  **not** retried and **not** re-run by the restart — it is lost until its next daily slot. Read the
  real duration from `details->>'duration_seconds'` on the `sec_edgar` `regulatory_data_state` row.
- **⚠️ Do NOT deploy during 03:15–09:45 or 12:55–14:00 UTC.** `./deploy.sh` now refuses inside those
  windows (`ALLOW_RISKY_DEPLOY=1` overrides). The first window covers the DSE session plus the US SEC
  crons; the second covers the DSE EOD chain. Restart churn can hang the worker's cron loop and
  silently drop the EOD jobs (2026-06-29), and it kills any in-flight SEC refresh outright
  (2026-08-06: a 06:21 deploy killed the 06:15 EDGAR pass; nothing surfaced it for 12 hours).
- **Watchdog:** `ingestion.watchdog` runs as an independent systemd timer (every 5 min) — checks
  worker liveness, intraday quote freshness, API health, and post-EOD data freshness; restarts the
  worker + emails `iliasfromberlin@gmail.com` on fault. Units in `infra/systemd/`.
- **Specs worth reading before touching these areas:** `docs/specs/trending-engine.md` (the "Active
  today" engine + regulatory posture + recovery runbook), `docs/specs/`. Descriptive-only / no
  buy-sell advice and **omit-over-mislead** are hard rules for all investor-facing data.
