#!/usr/bin/env bash
# Provision the dedicated Bulls Atlas static-site stack.
set -euo pipefail
cd "$(dirname "$0")/../.."

AWS=(aws --region "${ATLAS_AWS_REGION:-us-east-1}")
if [[ -n "${ATLAS_AWS_PROFILE:-}" ]]; then
  AWS+=(--profile "$ATLAS_AWS_PROFILE")
fi

: "${ATLAS_TENANT:?set ATLAS_TENANT to bullsofdhaka or bullsofwallst}"
TENANT_CONFIG="tenants/$ATLAS_TENANT/tenant.toml"
[[ -f "$TENANT_CONFIG" ]] || { echo "Unknown tenant: $ATLAS_TENANT" >&2; exit 2; }
IFS=$'\t' read -r TENANT_NAME DOMAIN_NAME ALIAS_DOMAIN_NAME API_URL < <(python3 - "$TENANT_CONFIG" <<'PY'
import pathlib, sys, tomllib
from urllib.parse import urlparse
config = tomllib.loads(pathlib.Path(sys.argv[1]).read_text())
aliases = config.get("research_alias_urls", [])
if len(aliases) > 1:
    raise SystemExit("the Atlas stack currently supports one branded alias per tenant")
print("\t".join((
    config["name"],
    urlparse(config["research_site_url"]).hostname,
    urlparse(aliases[0]).hostname if aliases else "",
    config["research_api_url"],
)))
PY
)

CALLER_JSON="$("${AWS[@]}" sts get-caller-identity --output json)"
CALLER_ARN="$(printf '%s' "$CALLER_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["Arn"])')"
ACCOUNT_ID="$(printf '%s' "$CALLER_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["Account"])')"

if [[ "$CALLER_ARN" == *":root" ]]; then
  echo "Refusing to provision with the AWS root principal. Configure ATLAS_AWS_PROFILE." >&2
  exit 1
fi

: "${ATLAS_HOSTED_ZONE_ID:?set ATLAS_HOSTED_ZONE_ID for $DOMAIN_NAME}"
STACK_NAME="${ATLAS_STACK_NAME:-bulls-atlas-$TENANT_NAME}"
BUCKET_NAME="${ATLAS_S3_BUCKET:-bulls-atlas-$TENANT_NAME-$ACCOUNT_ID}"
HOSTED_ZONE_ID="$ATLAS_HOSTED_ZONE_ID"
CERTIFICATE_ARN="${ATLAS_CERTIFICATE_ARN:-}"

"${AWS[@]}" cloudformation deploy \
  --stack-name "$STACK_NAME" \
  --template-file infra/aws/bulls-atlas-static-site.yml \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    DomainName="$DOMAIN_NAME" \
    AliasDomainName="$ALIAS_DOMAIN_NAME" \
    HostedZoneId="$HOSTED_ZONE_ID" \
    CertificateArn="$CERTIFICATE_ARN" \
    SiteBucketName="$BUCKET_NAME" \
    ResearchApiUrl="$API_URL"

"${AWS[@]}" cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs[].{Key:OutputKey,Value:OutputValue}' \
  --output table
