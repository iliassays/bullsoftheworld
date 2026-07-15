#!/usr/bin/env bash
# One-command backend release for the Bulls of the World production host.
#
#   ./deploy.sh
#
# Pushes the current branch to origin/main, builds the frontend locally (the
# server has no Node), ships the build, then on the server: pulls, syncs deps,
# runs migrations, and restarts the API / hedge / worker services.
set -euo pipefail
cd "$(dirname "$0")"

: "${DEPLOY_SSH_HOST:?set DEPLOY_SSH_HOST to your production SSH host or config alias}"
REMOTE="$DEPLOY_SSH_HOST"
APP=/home/ubuntu/bullsofdhaka
API_URL=https://api.bullsofdhaka.com
SITE_URL=https://bullsofdhaka.com

echo "→ pushing code to origin/main"
# Port 22 to github.com is often blocked on this network; fall back to the 443 SSH endpoint.
GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=8" \
  git push origin HEAD:main 2>/dev/null || git \
  -c core.sshCommand="ssh -i ~/.ssh/github_iliassays -p 443 -o HostName=ssh.github.com -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" \
  push origin HEAD:main

echo "→ building frontend (VITE_API_BASE=$API_URL)"
(
  cd apps/web
  VITE_API_BASE="$API_URL" \
  VITE_DEFAULT_LANG=bn \
  VITE_SITE_URL="$SITE_URL" \
  VITE_HTML_TITLE="Bulls of Dhaka" \
  VITE_HTML_DESCRIPTION="Bulls of Dhaka - facts on the DSE, not rumours. Live delayed prices, daily market signals, and a community for Bangladeshi retail investors. Descriptive data, not financial advice." \
  VITE_OG_SITE_NAME="Bulls of Dhaka" \
  VITE_OG_TITLE="Bulls of Dhaka - Facts, not rumours" \
  VITE_OG_DESCRIPTION="Live DSE data, daily market signals, and a community for Bangladeshi retail investors. Descriptive data, not financial advice." \
  VITE_TWITTER_TITLE="Bulls of Dhaka - Facts, not rumours" \
  VITE_TWITTER_DESCRIPTION="Live DSE data, daily market signals, and a community for Bangladeshi retail investors." \
  VITE_GA_ID="G-WPD860DBCK" \
  VITE_GTM_ID="GTM-KJWW62ZH" \
  npm run build
)

echo "→ shipping frontend build"
rsync -az --delete apps/web/dist/ "$REMOTE:$APP/apps/web/dist/"

echo "→ updating backend on $REMOTE"
ssh "$REMOTE" "cd $APP \
  && git pull -q origin main \
  && ~/.local/bin/uv sync -q \
  && ( test -r /home/ubuntu/.config/bulls/migration.env \
       || ~/.local/bin/uv run python scripts/bootstrap_runtime_db_credentials.py ) \
  && test -r /home/ubuntu/.config/bulls/migration.env \
  && set -a \
  && . /home/ubuntu/.config/bulls/migration.env \
  && set +a \
  && ( cd services/api && ~/.local/bin/uv run alembic upgrade head ) \
  && ~/.local/bin/uv run python scripts/provision_runtime_db_role.py \
  && sudo cp infra/systemd/bulls-ai-worker.service \
       /etc/systemd/system/bullsofdhaka-ai-worker.service \
  && sudo cp infra/systemd/bullsofwallst-worker.service \
       infra/systemd/bullsofwallst-sec-worker.service \
       infra/systemd/bullsofwallst-research-worker.service \
       infra/systemd/bullsofwallst-sec-watchdog.service \
       infra/systemd/bullsofwallst-sec-watchdog.timer \
       /etc/systemd/system/ \
  && sudo systemctl daemon-reload \
  && sudo systemctl enable bullsofdhaka-ai-worker bullsofwallst-worker bullsofwallst-sec-worker \
       bullsofwallst-research-worker bullsofwallst-sec-watchdog.timer \
  && sudo systemctl restart bullsofdhaka-api bullsofdhaka-hedge bullsofdhaka-worker \
       bullsofdhaka-ai-worker bullsofwallst-worker bullsofwallst-sec-worker \
       bullsofwallst-research-worker bullsofwallst-sec-watchdog.timer"

echo "✓ released backend and server assets for $SITE_URL"
