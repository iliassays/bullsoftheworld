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
#   WEB_HTML_TITLE      Static index.html title
#   WEB_SITE_DESCRIPTION Static index.html meta description
#   WEB_GA_ID           GA4 measurement id, default G-WPD860DBCK (Bulls of Dhaka's property)
#   WEB_GTM_ID           GTM container id, default GTM-KJWW62ZH (Bulls of Dhaka's container)
#   WEB_SITEMAP_RESOLVE_IP Override DNS only for build-time API reads (TLS still verifies hostname)
set -euo pipefail
cd "$(dirname "$0")"

: "${WEB_S3_BUCKET:?set WEB_S3_BUCKET (the S3 bucket name)}"
: "${WEB_CLOUDFRONT_ID:?set WEB_CLOUDFRONT_ID (the CloudFront distribution id)}"

SITE_URL="${WEB_SITE_URL:-https://bullsofdhaka.com}"
SITE_URL="${SITE_URL%/}"
API_URL="${WEB_API_URL:-https://api.bullsofdhaka.com}"
BRAND_NAME="${WEB_BRAND_NAME:-Bulls of Dhaka}"
DEFAULT_LANG="${WEB_DEFAULT_LANG:-bn}"
HTML_TITLE="${WEB_HTML_TITLE:-$BRAND_NAME}"
SITE_DESCRIPTION="${WEB_SITE_DESCRIPTION:-$BRAND_NAME - market data, ticker search, daily signals, and a community for retail investors. Descriptive data, not financial advice.}"
OG_TITLE="${WEB_OG_TITLE:-$BRAND_NAME - Market data, not noise}"
OG_DESCRIPTION="${WEB_OG_DESCRIPTION:-$SITE_DESCRIPTION}"
TWITTER_TITLE="${WEB_TWITTER_TITLE:-$OG_TITLE}"
TWITTER_DESCRIPTION="${WEB_TWITTER_DESCRIPTION:-$OG_DESCRIPTION}"
GA_ID="${WEB_GA_ID:-G-WPD860DBCK}"
GTM_ID="${WEB_GTM_ID:-GTM-KJWW62ZH}"

echo "→ building frontend (VITE_API_BASE=$API_URL, GA=$GA_ID, GTM=$GTM_ID)"
(
  cd apps/web
  VITE_API_BASE="$API_URL" \
  VITE_DEFAULT_LANG="$DEFAULT_LANG" \
  VITE_SITE_URL="$SITE_URL" \
  VITE_HTML_TITLE="$HTML_TITLE" \
  VITE_HTML_DESCRIPTION="$SITE_DESCRIPTION" \
  VITE_OG_SITE_NAME="$BRAND_NAME" \
  VITE_OG_TITLE="$OG_TITLE" \
  VITE_OG_DESCRIPTION="$OG_DESCRIPTION" \
  VITE_TWITTER_TITLE="$TWITTER_TITLE" \
  VITE_TWITTER_DESCRIPTION="$TWITTER_DESCRIPTION" \
  VITE_GA_ID="$GA_ID" \
  VITE_GTM_ID="$GTM_ID" \
  npm run build
)

echo "→ generating sitemap.xml + robots.txt ($SITE_URL)"
WEB_API_URL="$API_URL" WEB_SITE_URL="$SITE_URL" WEB_SITEMAP_STRICT=1 node scripts/gen_sitemap.mjs

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
