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
