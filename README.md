# Bulls of the World 🐂

A multi-tenant social platform for stock markets — post, follow, tag stocks with cashtags
(`$GP`), call bull/bear, and watch the market. One engine, localized faces.

> **First tenant:** [Bulls of Dhaka](tenants/bullsofdhaka) — Dhaka Stock Exchange (DSE), Bangla-first.

## Architecture at a glance

```
apps/web            React PWA (Bangla-first, dark, mobile-fast)
services/
  api               FastAPI — auth, feed, posts, cashtags, WebSocket
  ingestion         market-data adapters + scheduler
  ai_worker         async AI jobs (never blocks a request)
packages/
  core              config, tenancy, db, models      (bulls.core)
  market_data       provider interface + DSE adapter  (bulls.market_data)  ← the crux
  ai                Claude client, RAG, evals         (bulls.ai)
tenants/            per-market config (market, locale, branding)
```

The app only ever talks to a `MarketDataProvider` — swapping the DSE scraper for a licensed
real-time feed is a one-line registry change. See [CLAUDE.md](CLAUDE.md) for principles.

## Quickstart

```bash
cp .env.example .env
uv sync
docker compose -f infra/docker-compose.yml up -d        # postgres (5433) + redis
cd services/api && uv run alembic upgrade head && cd ../..
uv run python -m ingestion.main DSE                     # seed live DSE data
uv run granian --interface asgi api.main:app --port 8090
# api docs at http://localhost:8090/docs

cd apps/web && npm install && npm run dev               # web at http://localhost:5173
```

> Ports: this project uses Postgres **5433** and API **8090** (a local Postgres
> already owns 5432 and another service owns 8000).

### Keeping data fresh (scheduler)

A long-lived arq worker refreshes DSE data on the market's clock — intraday quote polls during the
session and an end-of-day bar pull after the close — so you don't run ingestion by hand:

```bash
uv run arq ingestion.worker.WorkerSettings   # deploy in UTC; schedules are UTC (Dhaka = UTC+6, no DST)
```

It replaces the old laptop launchd job. Every job re-checks the DSE trading calendar before acting.

## Design

UI direction (dark-first, Bull Gold, Bangla typography): [design/bulls-of-dhaka-ui.html](design/bulls-of-dhaka-ui.html)
