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
WEB_S3_BUCKET="$PROD_S3_BUCKET" \
WEB_CLOUDFRONT_ID="$PROD_CLOUDFRONT_ID" \
WEB_API_URL="${PROD_API_URL:-https://api.bullsofdhaka.com}" \
WEB_SITE_URL="${PROD_SITE_URL:-https://bullsofdhaka.com}" \
WEB_TENANT_HOST="${PROD_TENANT_HOST:-bullsofdhaka.com}" \
WEB_BRAND_NAME="${PROD_BRAND_NAME:-Bulls of Dhaka}" \
WEB_DEFAULT_LANG="${PROD_DEFAULT_LANG:-bn}" \
WEB_HTML_TITLE="${PROD_HTML_TITLE:-Bulls of Dhaka}" \
WEB_SITE_DESCRIPTION="${PROD_SITE_DESCRIPTION:-Bulls of Dhaka - facts on the DSE, not rumours. Live delayed prices, daily market signals, and a community for Bangladeshi retail investors. Descriptive data, not financial advice.}" \
WEB_OG_TITLE="${PROD_OG_TITLE:-Bulls of Dhaka - Facts, not rumours}" \
WEB_OG_DESCRIPTION="${PROD_OG_DESCRIPTION:-Live DSE data, daily market signals, and a community for Bangladeshi retail investors. Descriptive data, not financial advice.}" \
WEB_TWITTER_TITLE="${PROD_TWITTER_TITLE:-Bulls of Dhaka - Facts, not rumours}" \
WEB_TWITTER_DESCRIPTION="${PROD_TWITTER_DESCRIPTION:-Live DSE data, daily market signals, and a community for Bangladeshi retail investors.}" \
WEB_GA_ID="${PROD_GA_ID:-G-WPD860DBCK}" \
WEB_GTM_ID="${PROD_GTM_ID:-GTM-KJWW62ZH}" \
./deploy-web.sh
