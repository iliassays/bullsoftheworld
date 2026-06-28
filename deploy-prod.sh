#!/usr/bin/env bash
# Deploy the PRODUCTION frontend (bullsofdhaka.com) to S3 + CloudFront.
#
#   ./deploy-prod.sh
#
# Prereqs (one-time):
#   1. aws CLI installed + configured:  aws configure   (IAM user with S3 + CloudFront access)
#   2. export these (or put in a local, gitignored prod.env and `source` it):
#        export PROD_S3_BUCKET=bullsofdhaka-web        # the S3 bucket name
#        export PROD_CLOUDFRONT_ID=E123ABC...          # CloudFront distribution id
#
# The API stays on the server; only the static frontend ships here. Built against the prod API.
set -euo pipefail
cd "$(dirname "$0")"

: "${PROD_S3_BUCKET:?set PROD_S3_BUCKET (the S3 bucket name)}"
: "${PROD_CLOUDFRONT_ID:?set PROD_CLOUDFRONT_ID (the CloudFront distribution id)}"
API_URL="${PROD_API_URL:-https://api.bullsofdhaka.com}"

echo "→ building frontend (VITE_API_BASE=$API_URL)"
( cd apps/web && VITE_API_BASE="$API_URL" npm run build )

# Only the hashed /assets/* bundles are content-addressed → safe to cache forever.
echo "→ syncing hashed assets to s3://$PROD_S3_BUCKET/assets (immutable)"
aws s3 sync apps/web/dist/assets/ "s3://$PROD_S3_BUCKET/assets/" --delete \
  --cache-control "public,max-age=31536000,immutable"

# Stable-named root files (favicons, logo-mark, og, manifest, pwa icons) keep their names
# across rebrands, so they must NOT be immutable — short cache + revalidate so a rebrand
# actually reaches visitors. (This was the bug: a new logo never propagated.)
echo "→ syncing root files (short cache, revalidate)"
aws s3 sync apps/web/dist/ "s3://$PROD_S3_BUCKET/" --delete \
  --exclude "assets/*" --exclude "index.html" \
  --cache-control "public,max-age=300,must-revalidate"

echo "→ uploading index.html (no-store)"
aws s3 cp apps/web/dist/index.html "s3://$PROD_S3_BUCKET/index.html" \
  --cache-control "no-store" --content-type "text/html; charset=utf-8"

echo "→ invalidating CloudFront cache"
aws cloudfront create-invalidation \
  --distribution-id "$PROD_CLOUDFRONT_ID" --paths "/" "/index.html" >/dev/null

echo "✓ deployed → https://bullsofdhaka.com"
