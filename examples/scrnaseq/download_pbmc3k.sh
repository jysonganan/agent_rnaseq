#!/usr/bin/env bash
# Download the 10x Genomics PBMC 3k public dataset.
#
# This script downloads the raw FASTQ files (~4 GB) and the pre-built
# Cell Ranger reference transcriptome for GRCh38 (~11 GB).
# Total disk required: ~15 GB.
#
# Usage:
#   bash download_pbmc3k.sh [--data-dir <dir>]
#
# Options:
#   --data-dir   Destination directory (default: ./data)

set -euo pipefail

DATA_DIR="./data"

# ── Parse arguments ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --data-dir)
      DATA_DIR="$2"
      shift 2
      ;;
    -h|--help)
      head -n 20 "$0" | grep '^#' | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

mkdir -p "$DATA_DIR"

# ── PBMC 3k FASTQs (10x Genomics v1 chemistry, ~4 GB) ───────────────────────
FASTQ_URL="https://cf.10xgenomics.com/samples/cell-exp/1.1.0/pbmc3k/pbmc3k_fastqs.tar"
FASTQ_TAR="$DATA_DIR/pbmc3k_fastqs.tar"
FASTQ_DIR="$DATA_DIR/fastqs"

if [[ ! -d "$FASTQ_DIR" ]]; then
  echo "Downloading PBMC 3k FASTQs..."
  curl -L --retry 3 -o "$FASTQ_TAR" "$FASTQ_URL"
  echo "Extracting FASTQs..."
  mkdir -p "$FASTQ_DIR"
  tar -xf "$FASTQ_TAR" -C "$FASTQ_DIR"
  rm -f "$FASTQ_TAR"
  echo "FASTQs ready at: $FASTQ_DIR"
else
  echo "FASTQ directory already exists, skipping download: $FASTQ_DIR"
fi

# ── GRCh38 Cell Ranger reference (~11 GB) ────────────────────────────────────
REF_URL="https://cf.10xgenomics.com/supp/cell-exp/refdata-gex-GRCh38-2020-A.tar.gz"
REF_TAR="$DATA_DIR/refdata-gex-GRCh38-2020-A.tar.gz"
REF_DIR="$DATA_DIR/refdata-gex-GRCh38-2020-A"

if [[ ! -d "$REF_DIR" ]]; then
  echo "Downloading GRCh38 Cell Ranger reference..."
  curl -L --retry 3 -o "$REF_TAR" "$REF_URL"
  echo "Extracting reference..."
  tar -xzf "$REF_TAR" -C "$DATA_DIR"
  rm -f "$REF_TAR"
  echo "Reference ready at: $REF_DIR"
else
  echo "Reference already exists, skipping download: $REF_DIR"
fi

echo ""
echo "=== Download complete ==="
echo "FASTQ directory : $FASTQ_DIR"
echo "Reference       : $REF_DIR"
echo ""
echo "Next steps:"
echo "  1. Run CellRanger via the agent API (see README.md) or directly:"
echo "     cellranger count \\"
echo "       --id=pbmc3k \\"
echo "       --fastqs=$FASTQ_DIR \\"
echo "       --transcriptome=$REF_DIR \\"
echo "       --localcores=8 --localmem=64"
echo "  2. Open examples/scrnaseq/analysis.ipynb for the Scanpy walkthrough."
