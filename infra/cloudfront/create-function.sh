#!/usr/bin/env bash
# Create + publish the bot-router CloudFront Function. Idempotent-ish: creates on first run, and
# on later runs updates the existing function to the current bot-router.js and republishes.
#
# This ONLY manages the Function itself (safe, isolated). Associating it with the distribution and
# adding the API origin + /seo/* behavior are distribution-config edits — see README.md; do those
# in the console or with the documented CLI sequence after this succeeds.
#
#   aws configure   # once, with CloudFront permissions
#   ./infra/cloudfront/create-function.sh
set -euo pipefail
cd "$(dirname "$0")"

NAME="${CF_FUNCTION_NAME:-bulls-bot-router}"
SRC="bot-router.js"

exists() { aws cloudfront describe-function --name "$NAME" >/dev/null 2>&1; }

if exists; then
  ETAG=$(aws cloudfront describe-function --name "$NAME" --query 'ETag' --output text)
  echo "→ updating existing function $NAME (ETag $ETAG)"
  aws cloudfront update-function \
    --name "$NAME" \
    --if-match "$ETAG" \
    --function-config "Comment=SEO bot router,Runtime=cloudfront-js-2.0" \
    --function-code "fileb://$SRC" >/dev/null
else
  echo "→ creating function $NAME"
  aws cloudfront create-function \
    --name "$NAME" \
    --function-config "Comment=SEO bot router,Runtime=cloudfront-js-2.0" \
    --function-code "fileb://$SRC" >/dev/null
fi

ETAG=$(aws cloudfront describe-function --name "$NAME" --query 'ETag' --output text)
echo "→ publishing (ETag $ETAG)"
aws cloudfront publish-function --name "$NAME" --if-match "$ETAG" >/dev/null
echo "✓ function '$NAME' published. Now associate it + add the /seo/* behavior — see README.md"
