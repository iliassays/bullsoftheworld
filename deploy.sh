#!/usr/bin/env bash
# One-command deploy to bullstreetai (bullsofdhaka.bullstreetai.com).
#
#   ./deploy.sh
#
# Pushes the current branch to origin/main, builds the frontend locally (the
# server has no Node), ships the build, then on the server: pulls, syncs deps,
# runs migrations, and restarts the API / hedge / worker services.
set -euo pipefail
cd "$(dirname "$0")"

REMOTE=bullstreetai
APP=/home/ubuntu/bullsofdhaka
API_URL=https://bullsofdhaka-api.bullstreetai.com

echo "→ pushing code to origin/main"
git push origin HEAD:main

echo "→ building frontend (VITE_API_BASE=$API_URL)"
( cd apps/web && VITE_API_BASE="$API_URL" npm run build )

echo "→ shipping frontend build"
rsync -az --delete apps/web/dist/ "$REMOTE:$APP/apps/web/dist/"

echo "→ updating backend on $REMOTE"
ssh "$REMOTE" "cd $APP \
  && git pull -q origin main \
  && ~/.local/bin/uv sync -q \
  && ( cd services/api && ~/.local/bin/uv run alembic upgrade head ) \
  && sudo systemctl restart bullsofdhaka-api bullsofdhaka-hedge bullsofdhaka-worker bullsofdhaka-ai-worker"

echo "✓ deployed → https://bullsofdhaka.bullstreetai.com"
