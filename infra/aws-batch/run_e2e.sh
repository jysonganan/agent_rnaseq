#!/usr/bin/env bash
# Real end-to-end run on AWS Batch (L3): synthetic data → S3 → Nextflow -profile awsbatch →
# verification against truth.json. Prints a PASS/FAIL table and writes e2e_report.json.
#
# Usage: infra/aws-batch/run_e2e.sh [--stages qc,alignment,quantification,variant_calling]
#                                   [--with-de]   # also DESeq2 (needs R + DESeq2 on this host)
# Requires on this host: Java 17 + Nextflow 23.10.1 (the worker is the Nextflow head),
# aws CLI, Docker (to build the tiny reference with the tools image), and e2e.env from
# deploy.sh + build_push_tools_image.sh.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${HERE}/../.." && pwd)"
source "${HERE}/e2e.env"
: "${NEXTFLOW_TOOLS_IMAGE:?run build_push_tools_image.sh first}"

STAGES="qc,alignment,quantification,variant_calling"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --stages) STAGES="$2"; shift 2 ;;
    --with-de) STAGES="${STAGES},differential_expression"; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
for c in java nextflow aws docker; do
  command -v "$c" >/dev/null || { echo "missing prerequisite: $c" >&2; exit 1; }
done

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="${E2E_WORK_DIR:-${HOME}/.agent_rnaseq_e2e/aws-${STAMP}}"
mkdir -p "$WORK"
python3 "${ROOT}/scripts/e2e/make_test_data.py" --out "${WORK}/data"
aws ecr get-login-password --region "$AWS_DEFAULT_REGION" \
  | docker login --username AWS --password-stdin "${NEXTFLOW_TOOLS_IMAGE%%/*}" >/dev/null
"${ROOT}/scripts/e2e/prepare_reference.sh" "${WORK}/data" --docker "$NEXTFLOW_TOOLS_IMAGE"

cd "$ROOT"
E2E_EXECUTOR=aws_batch \
E2E_DATA_DIR="${WORK}/data" \
E2E_OUTPUT_ROOT="${WORK}/out" \
E2E_STAGES="$STAGES" \
E2E_S3_PREFIX="s3://${S3_ARTIFACT_BUCKET}/e2e/${STAMP}" \
  python3 -m pytest tests/e2e/test_executor_e2e.py -v -s
echo "Report: ${WORK}/out/e2e_report.json  (S3 data expires per the bucket lifecycle)"
