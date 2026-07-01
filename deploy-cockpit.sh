#!/usr/bin/env bash
# Deploy the COCKPIT admin app (cockpit.bullsofdhaka.com) to its own S3 + CloudFront.
#
#   COCKPIT_S3_BUCKET=bullsofdhaka-cockpit COCKPIT_CLOUDFRONT_ID=E... ./deploy-cockpit.sh
#
# Isolated from the consumer site: its own bucket + distribution, so this never touches
# bullsofdhaka.com. Built against the prod API (shares api.bullsofdhaka.com).
set -euo pipefail
cd "$(dirname "$0")"

: "${COCKPIT_S3_BUCKET:?set COCKPIT_S3_BUCKET (the cockpit S3 bucket name)}"
: "${COCKPIT_CLOUDFRONT_ID:?set COCKPIT_CLOUDFRONT_ID (the cockpit CloudFront distribution id)}"
API_URL="${PROD_API_URL:-https://api.bullsofdhaka.com}"

echo "→ building cockpit (VITE_API_BASE=$API_URL)"
( cd apps/admin && VITE_API_BASE="$API_URL" npm run build )

echo "→ syncing hashed assets to s3://$COCKPIT_S3_BUCKET/assets (immutable)"
aws s3 sync apps/admin/dist/assets/ "s3://$COCKPIT_S3_BUCKET/assets/" --delete \
  --cache-control "public,max-age=31536000,immutable"

echo "→ uploading index.html (no-store)"
aws s3 cp apps/admin/dist/index.html "s3://$COCKPIT_S3_BUCKET/index.html" \
  --cache-control "no-store" --content-type "text/html; charset=utf-8"

echo "→ invalidating CloudFront cache"
aws cloudfront create-invalidation \
  --distribution-id "$COCKPIT_CLOUDFRONT_ID" --paths "/" "/index.html" >/dev/null

echo "✓ deployed → https://cockpit.bullsofdhaka.com"
