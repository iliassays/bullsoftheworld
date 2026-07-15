#!/usr/bin/env bash
# One-time local setup for short-lived BullsWebDeployer sessions.
set -euo pipefail

AWS=(aws --region "${BULLS_AWS_REGION:-us-east-1}")
if [[ -n "${BULLS_BOOTSTRAP_AWS_PROFILE:-}" ]]; then
  AWS+=(--profile "$BULLS_BOOTSTRAP_AWS_PROFILE")
fi

OPERATOR_USER="${BULLS_RELEASE_OPERATOR_NAME:-BullsReleaseOperator}"
ROLE_ARN="${BULLS_DEPLOYER_ROLE_ARN:?set BULLS_DEPLOYER_ROLE_ARN}"
SOURCE_PROFILE="${BULLS_RELEASE_SOURCE_PROFILE:-bulls-release-operator}"
DEPLOY_PROFILE="${BULLS_DEPLOYER_PROFILE:-bulls-deployer}"

CALLER_ARN="$("${AWS[@]}" sts get-caller-identity --query Arn --output text)"
if [[ "$CALLER_ARN" == *":root" && "${ALLOW_AWS_ROOT_BOOTSTRAP:-no}" != "yes" ]]; then
  echo "Root may only create the release-operator key with ALLOW_AWS_ROOT_BOOTSTRAP=yes." >&2
  exit 1
fi

KEY_COUNT="$("${AWS[@]}" iam list-access-keys \
  --user-name "$OPERATOR_USER" --query 'length(AccessKeyMetadata)' --output text)"
if [[ "$KEY_COUNT" != "0" ]]; then
  echo "$OPERATOR_USER already has an access key; refusing to create an untracked credential." >&2
  exit 1
fi

ACCESS_KEY_ID=""
SECRET_ACCESS_KEY=""
CONFIGURED=no
cleanup() {
  if [[ "$CONFIGURED" != "yes" && -n "$ACCESS_KEY_ID" ]]; then
    "${AWS[@]}" iam delete-access-key \
      --user-name "$OPERATOR_USER" --access-key-id "$ACCESS_KEY_ID" >/dev/null || true
  fi
  unset ACCESS_KEY_ID SECRET_ACCESS_KEY
}
trap cleanup EXIT

read -r ACCESS_KEY_ID SECRET_ACCESS_KEY < <("${AWS[@]}" iam create-access-key \
  --user-name "$OPERATOR_USER" \
  --query 'AccessKey.[AccessKeyId,SecretAccessKey]' --output text)

aws configure set aws_access_key_id "$ACCESS_KEY_ID" --profile "$SOURCE_PROFILE"
aws configure set aws_secret_access_key "$SECRET_ACCESS_KEY" --profile "$SOURCE_PROFILE"
aws configure set region "${BULLS_AWS_REGION:-us-east-1}" --profile "$SOURCE_PROFILE"
aws configure set role_arn "$ROLE_ARN" --profile "$DEPLOY_PROFILE"
aws configure set source_profile "$SOURCE_PROFILE" --profile "$DEPLOY_PROFILE"
aws configure set region "${BULLS_AWS_REGION:-us-east-1}" --profile "$DEPLOY_PROFILE"
chmod 600 "$HOME/.aws/credentials" "$HOME/.aws/config"

CONFIGURED=yes
aws --profile "$DEPLOY_PROFILE" sts get-caller-identity \
  --query '{Account:Account,Arn:Arn}' --output json
