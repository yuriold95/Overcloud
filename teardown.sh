#!/usr/bin/env bash
# Destroy every Overclouded stack in the active AWS profile, including buckets (auto-delete).
# Atlas is managed outside AWS: see docs/ATLAS_SETUP.md "Teardown".
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
: "${AWS_PROFILE:?Set AWS_PROFILE to your deployer profile}"
cd "$ROOT/infra"
mkdir -p "$ROOT/.lambda-build/bundle" "$ROOT/apps/web/dist"
npx --yes aws-cdk@2.1142.0 destroy --all --force --app "uv run python app.py"
echo "Remaining stacks named Overclouded-* (should be none):"
aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE UPDATE_ROLLBACK_COMPLETE DELETE_FAILED \
  --query "StackSummaries[?starts_with(StackName, 'Overclouded-')].StackName" --output text
echo "Secrets scheduled for deletion are removed after the recovery window; to purge now:"
echo "  aws secretsmanager delete-secret --secret-id overclouded/mongodb-uri --force-delete-without-recovery"
