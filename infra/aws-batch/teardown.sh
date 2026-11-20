#!/usr/bin/env bash
# Delete everything deploy.sh created: empties the bucket, deregisters the Nextflow job
# definitions that use the tools repository, deletes the stack (ECR images are removed with
# it). Irreversible — asks for the stack name to confirm.
#
# Usage: infra/aws-batch/teardown.sh [--yes]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "${HERE}/e2e.env"
if [[ "${1:-}" != "--yes" ]]; then
  read -r -p "Type the stack name (${E2E_STACK}) to delete it and all its data: " answer
  [[ "$answer" == "$E2E_STACK" ]] || { echo "aborted"; exit 1; }
fi

echo "Emptying s3://${S3_ARTIFACT_BUCKET}"
aws s3 rm "s3://${S3_ARTIFACT_BUCKET}" --recursive --only-show-errors || true

echo "Deregistering Nextflow job definitions for ${E2E_TOOLS_REPOSITORY}"
for arn in $(aws batch describe-job-definitions --status ACTIVE \
    --query "jobDefinitions[?starts_with(containerProperties.image, '${E2E_TOOLS_REPOSITORY}')].jobDefinitionArn" \
    --output text); do
  aws batch deregister-job-definition --job-definition "$arn"
done

echo "Deleting stack ${E2E_STACK}"
aws cloudformation delete-stack --stack-name "$E2E_STACK"
aws cloudformation wait stack-delete-complete --stack-name "$E2E_STACK"
rm -f "${HERE}/e2e.env"
echo "Done."
