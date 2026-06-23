---
name: run
description: Launch the Bulls of the World stack locally (Postgres + Redis + API + web) to see changes working.
---

# /run — launch the stack

Ports note: this dev machine already runs a Postgres on 5432 and a server on 8000, so this project
uses **Postgres host port 5433** and **API port 8090** to avoid clashing.

1. Ensure `.env` exists (`cp .env.example .env` if not).
2. Bring up infra: `docker compose -f infra/docker-compose.yml up -d` (wait for healthchecks).
3. `uv sync` if dependencies changed.
4. Apply migrations (first run): `cd services/api && uv run alembic upgrade head`
5. Seed data: `uv run python -m ingestion.main DSE` (pulls live DSE quotes into Postgres).
6. Run the API: `uv run granian --interface asgi api.main:app --host 127.0.0.1 --port 8090 --reload --reload-paths services --reload-paths packages`
   (Only watch source dirs — watching the repo root reloads on .ruff_cache/.venv churn and kills in-flight requests.)
   Verify: http://localhost:8090/docs, `/whoami` → tenant `bullsofdhaka`.
   For local AI: `brew services start ollama` and run the worker: `uv run arq ai_worker.worker.WorkerSettings`.
7. Run the web: `cd apps/web && npm install && npm run dev` → http://localhost:5173
   (web calls the API at http://localhost:8090; override with `VITE_API_BASE`).
