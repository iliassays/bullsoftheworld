#!/usr/bin/env bash
# Deploy the Bulls of Wall Street tenant through the shared S3/CloudFront web pipeline.
set -euo pipefail
cd "$(dirname "$0")"

: "${WALLST_S3_BUCKET:?set WALLST_S3_BUCKET (the S3 bucket name)}"
: "${WALLST_CLOUDFRONT_ID:?set WALLST_CLOUDFRONT_ID (the CloudFront distribution id)}"

WEB_S3_BUCKET="$WALLST_S3_BUCKET" \
WEB_CLOUDFRONT_ID="$WALLST_CLOUDFRONT_ID" \
WEB_API_URL="${WALLST_API_URL:-https://api.bullsofwallst.com}" \
WEB_SITE_URL="${WALLST_SITE_URL:-https://bullsofwallst.com}" \
WEB_TENANT_HOST="${WALLST_TENANT_HOST:-bullsofwallst.com}" \
WEB_BRAND_NAME="${WALLST_BRAND_NAME:-Bulls of Wall Street}" \
WEB_DEFAULT_LANG="${WALLST_DEFAULT_LANG:-en}" \
WEB_LANGS="${WALLST_LANGS:-en,bn}" \
WEB_HTML_TITLE="${WALLST_HTML_TITLE:-Bulls of Wall Street}" \
WEB_SITE_DESCRIPTION="${WALLST_SITE_DESCRIPTION:-US stock prices, price history, and a retail-investor community. Descriptive data, not financial advice.}" \
WEB_OG_TITLE="${WALLST_OG_TITLE:-Bulls of Wall Street - US market data, not noise}" \
WEB_OG_DESCRIPTION="${WALLST_OG_DESCRIPTION:-US stock prices, price history, and market discussion for retail investors.}" \
WEB_TWITTER_TITLE="${WALLST_TWITTER_TITLE:-Bulls of Wall Street - US market data, not noise}" \
WEB_TWITTER_DESCRIPTION="${WALLST_TWITTER_DESCRIPTION:-US stock prices, price history, and market discussion for retail investors.}" \
WEB_SITEMAP_RESOLVE_IP="${WALLST_SITEMAP_RESOLVE_IP:-}" \
./deploy-web.sh
