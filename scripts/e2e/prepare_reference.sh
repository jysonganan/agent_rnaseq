#!/usr/bin/env bash
# Build the indices the pipeline needs for the e2e reference (output of make_test_data.py):
#   reference/genome.fa.fai      samtools faidx          (GATK, bamCoverage)
#   reference/genome.dict        gatk CreateSequenceDictionary (GATK)
#   reference/star/              STAR genomeGenerate (with GTF junctions)
#
# Usage:
#   scripts/e2e/prepare_reference.sh <data_dir>                       # tools on PATH (conda env)
#   scripts/e2e/prepare_reference.sh <data_dir> --docker <tools-image> # tools from the image
#   scripts/e2e/prepare_reference.sh <data_dir> --stub                # placeholders (stub runs)
set -euo pipefail

DATA_DIR="${1:?usage: prepare_reference.sh <data_dir> [--docker IMAGE | --stub]}"
MODE="${2:-}"
IMAGE="${3:-}"
REF="$(cd "${DATA_DIR}/reference" && pwd)"

if [[ "${MODE}" == "--stub" ]]; then
  # Nextflow -stub-run only needs the inputs to exist.
  touch "${REF}/genome.fa.fai" "${REF}/genome.dict"
  mkdir -p "${REF}/star" && touch "${REF}/star/.stub"
  echo "stub reference placeholders written to ${REF}"
  exit 0
fi

run() {
  if [[ "${MODE}" == "--docker" ]]; then
    docker run --rm --platform linux/amd64 -u "$(id -u):$(id -g)" \
      -v "${REF}:${REF}" -w "${REF}" "${IMAGE:?--docker needs an image}" "$@"
  else
    (cd "${REF}" && "$@")
  fi
}

# STAR recommends genomeSAindexNbases = min(14, log2(genome_length)/2 - 1)
GENOME_LEN=$(grep -v '^>' "${REF}/genome.fa" | tr -d '\n' | wc -c | tr -d ' ')
SA_NBASES=$(python3 -c "import math; print(min(14, int(math.log2(${GENOME_LEN}) / 2 - 1)))")

run samtools faidx genome.fa
rm -f "${REF}/genome.dict"
run gatk CreateSequenceDictionary -R genome.fa -O genome.dict
mkdir -p "${REF}/star"
run STAR --runMode genomeGenerate \
  --genomeDir "${REF}/star" \
  --genomeFastaFiles "${REF}/genome.fa" \
  --sjdbGTFfile "${REF}/genes.gtf" \
  --sjdbOverhang 74 \
  --genomeSAindexNbases "${SA_NBASES}" \
  --runThreadN 2 \
  --outFileNamePrefix "${REF}/star/"

echo "reference ready in ${REF} (genome ${GENOME_LEN} bp, genomeSAindexNbases ${SA_NBASES})"
