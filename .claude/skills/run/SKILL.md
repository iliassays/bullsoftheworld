---
name: run
description: Launch the Bulls of the World stack locally (Postgres + Redis + API) to see changes working.
---

# /run — launch the stack

1. Ensure `.env` exists (`cp .env.example .env` if not).
2. Bring up infra: `docker compose -f infra/docker-compose.yml up -d` (wait for healthchecks).
3. `uv sync` if dependencies changed.
4. Run the API: `uv run granian --interface asgi api.main:app --port 8000`
5. Verify: open http://localhost:8000/docs, hit `/health` and `/whoami` (should return tenant `bullsofdhaka`).

For the web client: `cd apps/web && npm install && npm run dev`.
