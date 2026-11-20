#!/usr/bin/env bash
# Build docker/Dockerfile.tools for linux/amd64 and push it to the stack's ECR repository
# with an immutable tag (default: git short SHA). Appends NEXTFLOW_TOOLS_IMAGE to e2e.env.
#
# Usage: infra/aws-batch/build_push_tools_image.sh [tag]
# Requires: Docker with buildx, aws CLI. The image is large (R + Bioconductor + GATK); building
# needs ~25 GB free disk and can take 30–60 min (much longer under emulation on Apple Silicon —
# prefer an x86_64 build host or CI runner).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${HERE}/../.." && pwd)"
source "${HERE}/e2e.env"
TAG="${1:-$(git -C "$ROOT" rev-parse --short HEAD)}"
IMAGE="${E2E_TOOLS_REPOSITORY}:${TAG}"
REGISTRY="${E2E_TOOLS_REPOSITORY%%/*}"

aws ecr get-login-password --region "$AWS_DEFAULT_REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"
docker buildx build --platform linux/amd64 -f "${ROOT}/docker/Dockerfile.tools" \
  -t "$IMAGE" --push "$ROOT"

grep -v '^export NEXTFLOW_TOOLS_IMAGE=' "${HERE}/e2e.env" > "${HERE}/e2e.env.tmp" || true
mv "${HERE}/e2e.env.tmp" "${HERE}/e2e.env"
echo "export NEXTFLOW_TOOLS_IMAGE=${IMAGE}" >> "${HERE}/e2e.env"
echo "Pushed ${IMAGE}"
