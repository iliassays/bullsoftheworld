#!/usr/bin/env bash
# Idempotently wire crawler HTML rendering into a tenant CloudFront distribution.
set -euo pipefail

usage() {
  echo "usage: $0 <distribution-id> <api-domain>" >&2
  exit 2
}

[[ $# -eq 2 ]] || usage
command -v aws >/dev/null || { echo "aws CLI is required" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

DIST_ID="$1"
API_DOMAIN="$2"
API_ORIGIN_ID="tenant-api-seo"
FUNCTION_NAME="${CF_FUNCTION_NAME:-bulls-bot-router}"

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT
CURRENT="$WORK_DIR/current.json"
UPDATED="$WORK_DIR/updated.json"

aws cloudfront get-distribution-config --id "$DIST_ID" >"$CURRENT"
ETAG="$(jq -r '.ETag' "$CURRENT")"
FUNCTION_ARN="$(
  aws cloudfront describe-function \
    --name "$FUNCTION_NAME" \
    --stage LIVE \
    --query 'FunctionSummary.FunctionMetadata.FunctionARN' \
    --output text
)"

jq \
  --arg api_domain "$API_DOMAIN" \
  --arg api_origin_id "$API_ORIGIN_ID" \
  --arg function_arn "$FUNCTION_ARN" \
  '
  .DistributionConfig
  | .Origins.Items = (
      if any(.Origins.Items[]; .Id == $api_origin_id) then
        .Origins.Items
        | map(
            if .Id == $api_origin_id then
              .DomainName = $api_domain
              | .CustomOriginConfig.OriginProtocolPolicy = "https-only"
              | .CustomOriginConfig.OriginSslProtocols = {"Quantity": 1, "Items": ["TLSv1.2"]}
            else . end
          )
      else
        .Origins.Items + [{
          "Id": $api_origin_id,
          "DomainName": $api_domain,
          "OriginPath": "",
          "CustomHeaders": {"Quantity": 0},
          "CustomOriginConfig": {
            "HTTPPort": 80,
            "HTTPSPort": 443,
            "OriginProtocolPolicy": "https-only",
            "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]},
            "OriginReadTimeout": 30,
            "OriginKeepaliveTimeout": 5
          },
          "ConnectionAttempts": 3,
          "ConnectionTimeout": 10,
          "OriginShield": {"Enabled": false},
          "OriginAccessControlId": ""
        }]
      end
    )
  | .Origins.Quantity = (.Origins.Items | length)
  | .CacheBehaviors.Items = (
      (.CacheBehaviors.Items // [])
      | if any(.[]; .PathPattern == "/seo/*") then
          map(
            if .PathPattern == "/seo/*" then
              .TargetOriginId = $api_origin_id
              | .CachePolicyId = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
              | .OriginRequestPolicyId = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
            else . end
          )
        else
          . + [{
            "PathPattern": "/seo/*",
            "TargetOriginId": $api_origin_id,
            "TrustedSigners": {"Enabled": false, "Quantity": 0},
            "TrustedKeyGroups": {"Enabled": false, "Quantity": 0},
            "ViewerProtocolPolicy": "redirect-to-https",
            "AllowedMethods": {
              "Quantity": 2,
              "Items": ["HEAD", "GET"],
              "CachedMethods": {"Quantity": 2, "Items": ["HEAD", "GET"]}
            },
            "SmoothStreaming": false,
            "Compress": true,
            "LambdaFunctionAssociations": {"Quantity": 0},
            "FunctionAssociations": {"Quantity": 0},
            "FieldLevelEncryptionId": "",
            "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
            "OriginRequestPolicyId": "b689b0a8-53d0-40ab-baf2-68738e2966ac"
          }]
        end
    )
  | .CacheBehaviors.Quantity = (.CacheBehaviors.Items | length)
  | .DefaultCacheBehavior.FunctionAssociations.Items = (
      [(.DefaultCacheBehavior.FunctionAssociations.Items // [])[]
        | select(.EventType != "viewer-request")]
      + [{"FunctionARN": $function_arn, "EventType": "viewer-request"}]
    )
  | .DefaultCacheBehavior.FunctionAssociations.Quantity =
      (.DefaultCacheBehavior.FunctionAssociations.Items | length)
  | ([.DefaultCacheBehavior.TargetOriginId]
      + [(.CacheBehaviors.Items // [])[].TargetOriginId]) as $referenced_origins
  | .Origins.Items = [
      .Origins.Items[] as $origin
      | select(
          $origin.Id == $api_origin_id
          or $origin.DomainName != $api_domain
          or ($origin.Id | endswith("-api-seo") | not)
          or ($referenced_origins | index($origin.Id))
        )
      | $origin
    ]
  | .Origins.Quantity = (.Origins.Items | length)
  ' "$CURRENT" >"$UPDATED"

echo "Updating distribution $DIST_ID: /seo/* -> $API_DOMAIN; viewer requests -> $FUNCTION_NAME"
aws cloudfront update-distribution \
  --id "$DIST_ID" \
  --if-match "$ETAG" \
  --distribution-config "file://$UPDATED" \
  --query 'Distribution.{Id:Id,Status:Status,DomainName:DomainName}' \
  --output json
