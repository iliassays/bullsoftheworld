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
docker compose -f infra/docker-compose.yml up -d   # postgres + redis
uv run granian --interface asgi api.main:app --port 8000
# api docs at http://localhost:8000/docs
```

## Design

UI direction (dark-first, Bull Gold, Bangla typography): [design/bulls-of-dhaka-ui.html](design/bulls-of-dhaka-ui.html)
