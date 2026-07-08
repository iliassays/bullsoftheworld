# Bulls of the World

A multi-tenant social platform for stock markets — think "StockTwits, done local." Users post,
follow, tag stocks with cashtags (`$GP`), set sentiment (bull/bear), and watch market data.

- **Platform:** Bulls of the World (this repo, Python namespace `bulls`)
- **Tenant pattern:** Bulls of `[City]` → `bullsof[city].com`
- **First tenant:** Bulls of Dhaka — market `DSE`, locale `bn` (Bangla-first)

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

## Stack

| Layer | Choice |
|---|---|
| Language / packaging | Python 3.12+ / **uv** workspace |
| Web | **FastAPI** on **Granian** |
| DB | **Postgres + pgvector** (relational + JSON + vector + full-text in one) |
| ORM / migrations | **SQLAlchemy 2.0 async + Alembic** |
| Cache / queue / WS | **Redis** + **arq** |
| AI | **Claude API** (`anthropic`) — read the `/claude-api` skill before touching model code |
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
  CloudFront invalidate (bullsofdhaka.com). Server: `ssh bullstreetai`, app `/home/ubuntu/bullsofdhaka`,
  Postgres in docker (`docker compose -f infra/docker-compose.yml exec -T postgres psql -U bulls -d bulls -p 5432`).
- **Worker rhythm (arq cron, UTC, trading days):** intraday `poll_quotes` {4–8}:{0,15,30,45}; EOD chain
  `pull_eod_bars` 13:00 → `pull_eod_summary` 13:05 → `refresh_analytics` 13:15 → `run_trending` 13:25
  → `run_factor_signals` 13:40 → `run_market_signals` (Evening Wrap → feed+FB) 13:50; `run_morning_watch`
  3:30; `run_weekly_recap` Thu 14:00. arq weekday strings are `mon,tues,wed,thurs,fri,sat,sun`.
- **⚠️ Do NOT deploy during the session or the 13:00–13:50 UTC EOD window.** Heavy restart churn can
  hang the worker's cron loop and silently drop the EOD jobs (the 2026-06-29 incident). Batch changes
  outside those hours.
- **Watchdog:** `ingestion.watchdog` runs as an independent systemd timer (every 5 min) — checks
  worker liveness, intraday quote freshness, API health, and post-EOD data freshness; restarts the
  worker + emails `iliasfromberlin@gmail.com` on fault. Units in `infra/systemd/`.
- **Specs worth reading before touching these areas:** `docs/specs/trending-engine.md` (the "Active
  today" engine + regulatory posture + recovery runbook), `docs/specs/`. Descriptive-only / no
  buy-sell advice and **omit-over-mislead** are hard rules for all investor-facing data.
