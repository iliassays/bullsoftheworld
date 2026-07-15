#!/usr/bin/env bash
# One-time account bootstrap. All normal releases must assume the resulting role.
set -euo pipefail
cd "$(dirname "$0")/../.."

AWS=(aws --region "${BULLS_AWS_REGION:-us-east-1}")
if [[ -n "${BULLS_BOOTSTRAP_AWS_PROFILE:-}" ]]; then
  AWS+=(--profile "$BULLS_BOOTSTRAP_AWS_PROFILE")
fi

: "${DHAKA_HOSTED_ZONE_ID:?set DHAKA_HOSTED_ZONE_ID}"
: "${WALLST_HOSTED_ZONE_ID:?set WALLST_HOSTED_ZONE_ID}"

CALLER_ARN="$("${AWS[@]}" sts get-caller-identity --query Arn --output text)"
if [[ "$CALLER_ARN" == *":root" && "${ALLOW_AWS_ROOT_BOOTSTRAP:-no}" != "yes" ]]; then
  echo "Root may only run this one-time bootstrap with ALLOW_AWS_ROOT_BOOTSTRAP=yes." >&2
  exit 1
fi

"${AWS[@]}" cloudformation deploy \
  --stack-name "${BULLS_DEPLOYER_STACK_NAME:-bulls-web-deployer}" \
  --template-file infra/aws/bulls-web-deployer-role.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    RoleName="${BULLS_DEPLOYER_ROLE_NAME:-BullsWebDeployer}" \
    OperatorUserName="${BULLS_RELEASE_OPERATOR_NAME:-BullsReleaseOperator}" \
    DhakaHostedZoneId="$DHAKA_HOSTED_ZONE_ID" \
    WallStreetHostedZoneId="$WALLST_HOSTED_ZONE_ID"

"${AWS[@]}" cloudformation describe-stacks \
  --stack-name "${BULLS_DEPLOYER_STACK_NAME:-bulls-web-deployer}" \
  --query 'Stacks[0].Outputs[].{Key:OutputKey,Value:OutputValue}' \
  --output table
