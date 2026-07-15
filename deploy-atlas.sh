#!/usr/bin/env bash
# Build and publish Bulls Atlas to its dedicated S3/CloudFront stack.
set -euo pipefail
cd "$(dirname "$0")"

: "${ATLAS_TENANT:?set ATLAS_TENANT to bullsofdhaka or bullsofwallst}"
: "${ATLAS_S3_BUCKET:?set ATLAS_S3_BUCKET from the tenant stack SiteBucketName output}"
: "${ATLAS_CLOUDFRONT_ID:?set ATLAS_CLOUDFRONT_ID from the tenant stack DistributionId output}"

TENANT_CONFIG="tenants/$ATLAS_TENANT/tenant.toml"
[[ -f "$TENANT_CONFIG" ]] || { echo "Unknown tenant: $ATLAS_TENANT" >&2; exit 2; }
IFS=$'\t' read -r TENANT_NAME ATLAS_MARKET ATLAS_SITE_URL ATLAS_API_URL < <(python3 - "$TENANT_CONFIG" <<'PY'
import pathlib, sys, tomllib
config = tomllib.loads(pathlib.Path(sys.argv[1]).read_text())
print("\t".join(config[key] for key in ("name", "market", "research_site_url", "research_api_url")))
PY
)
ATLAS_PREVIEW="${ATLAS_PREVIEW:-false}"

AWS=(aws)
if [[ -n "${ATLAS_AWS_PROFILE:-}" ]]; then
  AWS+=(--profile "$ATLAS_AWS_PROFILE")
fi

CALLER_ARN="$("${AWS[@]}" sts get-caller-identity --query Arn --output text)"
if [[ "$CALLER_ARN" == *":root" ]]; then
  echo "Refusing to deploy with the AWS root principal. Use ATLAS_AWS_PROFILE for a scoped role." >&2
  exit 1
fi

if [[ "$ATLAS_PREVIEW" == "true" && "${ATLAS_ALLOW_PUBLIC_PREVIEW:-no}" != "yes" ]]; then
  echo "Preview deployment requires ATLAS_ALLOW_PUBLIC_PREVIEW=yes." >&2
  exit 1
fi

echo "Building Bulls Atlas (preview=$ATLAS_PREVIEW, api=$ATLAS_API_URL)"
(
  cd apps/research
  VITE_RESEARCH_API_URL="$ATLAS_API_URL" \
  VITE_RESEARCH_SITE_URL="$ATLAS_SITE_URL" \
  VITE_RESEARCH_TENANT="$TENANT_NAME" \
  VITE_RESEARCH_MARKET="$ATLAS_MARKET" \
  VITE_RESEARCH_PREVIEW="$ATLAS_PREVIEW" \
  npm run build
)

echo "Publishing immutable assets"
"${AWS[@]}" s3 sync apps/research/dist/assets/ "s3://$ATLAS_S3_BUCKET/assets/" --delete \
  --cache-control "public,max-age=31536000,immutable"

echo "Publishing root files"
"${AWS[@]}" s3 sync apps/research/dist/ "s3://$ATLAS_S3_BUCKET/" --delete \
  --exclude "assets/*" --exclude "index.html" \
  --cache-control "public,max-age=300,must-revalidate"

"${AWS[@]}" s3 cp apps/research/dist/index.html "s3://$ATLAS_S3_BUCKET/index.html" \
  --cache-control "no-store" --content-type "text/html; charset=utf-8"

echo "Invalidating CloudFront entry points"
"${AWS[@]}" cloudfront create-invalidation \
  --distribution-id "$ATLAS_CLOUDFRONT_ID" \
  --paths "/" "/index.html" "/robots.txt" >/dev/null

echo "Deployed Bulls Atlas to $ATLAS_SITE_URL"
