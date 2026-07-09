#!/usr/bin/env bash
# Deploy a tenant frontend to S3 + CloudFront.
#
# Required:
#   WEB_S3_BUCKET       S3 bucket name
#   WEB_CLOUDFRONT_ID  CloudFront distribution id
#
# Optional:
#   WEB_SITE_URL        Canonical site URL, default https://bullsofdhaka.com
#   WEB_API_URL         Shared API URL, default https://api.bullsofdhaka.com
#   WEB_TENANT_HOST     Tenant host sent while generating sitemap, default host from WEB_SITE_URL
#   WEB_BRAND_NAME      Brand name used in generated robots header
#   WEB_DEFAULT_LANG    x-default hreflang, default bn
#   WEB_LANGS           Comma-separated language list, default bn,en
set -euo pipefail
cd "$(dirname "$0")"

: "${WEB_S3_BUCKET:?set WEB_S3_BUCKET (the S3 bucket name)}"
: "${WEB_CLOUDFRONT_ID:?set WEB_CLOUDFRONT_ID (the CloudFront distribution id)}"

SITE_URL="${WEB_SITE_URL:-https://bullsofdhaka.com}"
API_URL="${WEB_API_URL:-https://api.bullsofdhaka.com}"

echo "→ building frontend (VITE_API_BASE=$API_URL)"
( cd apps/web && VITE_API_BASE="$API_URL" npm run build )

echo "→ generating sitemap.xml + robots.txt ($SITE_URL)"
WEB_API_URL="$API_URL" WEB_SITE_URL="$SITE_URL" node scripts/gen_sitemap.mjs

echo "→ syncing hashed assets to s3://$WEB_S3_BUCKET/assets (immutable)"
aws s3 sync apps/web/dist/assets/ "s3://$WEB_S3_BUCKET/assets/" --delete \
  --cache-control "public,max-age=31536000,immutable"

echo "→ syncing root files (short cache, revalidate)"
aws s3 sync apps/web/dist/ "s3://$WEB_S3_BUCKET/" --delete \
  --exclude "assets/*" --exclude "index.html" \
  --cache-control "public,max-age=300,must-revalidate"

echo "→ uploading index.html (no-store)"
aws s3 cp apps/web/dist/index.html "s3://$WEB_S3_BUCKET/index.html" \
  --cache-control "no-store" --content-type "text/html; charset=utf-8"

echo "→ invalidating CloudFront cache"
aws cloudfront create-invalidation \
  --distribution-id "$WEB_CLOUDFRONT_ID" --paths "/" "/index.html" "/sitemap.xml" "/robots.txt" >/dev/null

echo "✓ deployed → $SITE_URL"
