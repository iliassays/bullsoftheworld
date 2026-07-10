# Bulls of the World 🐂

A multi-tenant social platform for stock markets — post, follow, tag stocks with cashtags
(`$GP`), call bull/bear, and watch the market. One engine, localized faces.

> **First tenant:** [Bulls of Dhaka](tenants/bullsofdhaka) — Dhaka Stock Exchange (DSE), Bangla-first.
> **US tenant:** [Bulls of Wall Street](tenants/bullsofwallst) — US equities, English-first.

## Architecture at a glance

```
apps/web            React PWA (Bangla-first, dark, mobile-fast)
services/
  api               FastAPI — auth, feed, posts, cashtags, WebSocket
  ingestion         market-data adapters + scheduler
  ai_worker         async AI jobs (never blocks a request)
packages/
  core              config, tenancy, db, models       (bulls.core)
  analytics         descriptive TA engine (RSI, S/R)  (bulls.analytics)
  market_data       provider interface + DSE adapter  (bulls.market_data)  ← the crux
  ai                Claude/Ollama client, RAG, evals  (bulls.ai)
tenants/            per-market config (market, locale, branding, domains)
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

# API (auto-reloads on changes under services/ and packages/)
uv run granian --interface asgi api.main:app --port 8090 \
  --reload --reload-paths services --reload-paths packages
# api docs at http://localhost:8090/docs · sanity: http://localhost:8090/whoami

cd apps/web && npm install && npm run dev               # web at http://localhost:5173
```

> Ports: this project uses Postgres **5433** and API **8090** (a local Postgres
> already owns 5432 and another service owns 8000).

The web reads the API base from `VITE_API_BASE` (defaults to `http://127.0.0.1:8090`); type-check
and build the frontend with `npm run build`.

### Keeping data fresh (scheduler)

A long-lived arq worker refreshes DSE data on the market's clock — intraday quote polls during the
session and an end-of-day bar pull after the close — so you don't run ingestion by hand:

```bash
uv run arq ingestion.worker.WorkerSettings   # deploy in UTC; schedules are UTC (Dhaka = UTC+6, no DST)
```

It replaces the old laptop launchd job. Every job re-checks the DSE trading calendar before acting.

### AI features (sentiment tagging, digests) — optional

AI jobs run in a separate worker so they never block a web request. Local + free uses Ollama;
set `AI_PROVIDER=claude` (+ `ANTHROPIC_API_KEY`) in `.env` to use Claude instead.

```bash
brew services start ollama && ollama pull qwen2.5   # local model (Bangla-capable); skip if using Claude
uv run arq ai_worker.worker.WorkerSettings          # tags post sentiment, etc.
```

### Make it feel alive (dev)

Drive realistic crowd activity through the real API — personas with favourite tickers, price-coherent
posts, replies, reactions, watchers — so the feed looks lived-in and the whole chain is exercised
(cashtags → sentiment → buzz snapshot → digest → screener):

```bash
uv run python scripts/simulate_activity.py          # one-shot burst
uv run python scripts/simulate_activity.py --live   # continuous, paced on the market clock
uv run python scripts/simulate_activity.py --clean  # remove all sim_ users + their data
```

## Tests

```bash
uv run pytest                                        # python unit tests
ENV=test uv run python scripts/seed_test_reference_data.py
ENV=test DB_TESTS=1 DISABLE_RATELIMIT=1 uv run pytest # + integration tests (Postgres + Redis)
uv run ruff check . && uv run ruff format .          # lint + format
```

## Frontend Deploys

```bash
# Bulls of Dhaka production
PROD_S3_BUCKET=bullsofdhaka-web PROD_CLOUDFRONT_ID=EPJ7LAHUJDDMK ./deploy-prod.sh

# Bulls of Wall Street production
WEB_S3_BUCKET=bullsofwallst-web \
WEB_CLOUDFRONT_ID=E3DLOEKLM3136G \
WEB_SITE_URL=https://bullsofwallst.com \
WEB_TENANT_HOST=bullsofwallst.com \
WEB_BRAND_NAME="Bulls of Wall Street" \
WEB_DEFAULT_LANG=en \
WEB_API_URL=https://api.bullsofdhaka.com \
./deploy-web.sh
```

## Design

UI direction (dark-first, Bull Gold, Bangla typography): [design/bulls-of-dhaka-ui.html](design/bulls-of-dhaka-ui.html)
