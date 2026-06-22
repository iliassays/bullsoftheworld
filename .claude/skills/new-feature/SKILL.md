---
name: new-feature
description: Think-plan-execute template for adding a feature. Enforces the non-adhoc workflow.
---

# /new-feature — think, plan, execute

Never jump straight to code. Follow the order:

1. **Think** — restate the feature in one line. Which layer? (`core` / `market_data` / `ai` / `api` / `web`)
   Does it touch the tenant abstraction? Does it belong in `ai_worker` (anything that calls an LLM)?
2. **Plan** — list the files to change, the data model delta (+ Alembic migration?), and the test
   you'll write first. If it's an AI feature, name the **eval set** — no AI merges without one.
3. **Check principles** (see CLAUDE.md): AI never blocks a request; app never touches a data source
   directly; core stays tenant-agnostic; never fake data freshness.
4. **Execute** — write the test, implement, `uv run ruff check . && uv run pytest`.
5. **Verify** — run it via `/run` and observe real behavior.
