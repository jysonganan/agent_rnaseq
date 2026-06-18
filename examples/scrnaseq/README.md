# Single-Cell RNA-seq Example

This directory contains an example dataset and notebook demonstrating the scRNA-seq pipeline.

## Overview

The example walks through:
1. Running CellRanger on a 10x Genomics PBMC dataset
2. Scanpy preprocessing (QC filtering, normalization, HVG selection)
3. Clustering and UMAP visualization
4. Marker gene identification per cluster

## Prerequisites

- CellRanger installed and on `$PATH`
- Reference transcriptome (e.g., `refdata-gex-GRCh38-2020-A`)
- Example FASTQ files (see below)

## Getting Example Data

The 10x Genomics PBMC 3k dataset is publicly available:

```bash
# Download raw FASTQs (~4 GB)
wget https://cf.10xgenomics.com/samples/cell-exp/1.1.0/pbmc3k/pbmc3k_fastqs.tar
tar -xf pbmc3k_fastqs.tar
```

## Running via the Agent API

```bash
# 1. Register the reference genome
curl -X POST http://localhost:8000/api/v1/genomes \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "GRCh38_2020A",
    "species": "homo_sapiens",
    "build": "GRCh38",
    "fasta_path": "/path/to/refdata-gex-GRCh38-2020-A/fasta/genome.fa",
    "gtf_path": "/path/to/refdata-gex-GRCh38-2020-A/genes/genes.gtf"
  }'

# 2. Create a project
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "PBMC 3k Example", "owner": "example-user"}'

# 3. Register the sample
curl -X POST http://localhost:8000/api/v1/projects/{project_id}/samples \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "samples": [{
      "name": "pbmc3k",
      "sample_type": "scrna_seq",
      "fastq_r1_path": "/path/to/pbmc3k_fastqs/pbmc3k_S1_L001_R1_001.fastq.gz",
      "fastq_r2_path": "/path/to/pbmc3k_fastqs/pbmc3k_S1_L001_R2_001.fastq.gz",
      "is_paired_end": true
    }]
  }'

# 4. Launch the scRNA-seq pipeline
curl -X POST http://localhost:8000/api/v1/runs \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "{project_id}",
    "genome_id": "{genome_id}",
    "name": "pbmc3k_scrna_run",
    "pipeline_type": "scrna_seq",
    "sample_ids": ["{sample_id}"],
    "stages": ["scrna_seq", "visualization", "report"],
    "execution": {"executor": "local", "cpus": 8, "memory_gb": 32}
  }'
```

## Expected Outputs

| Artifact | Description |
|---|---|
| `filtered_matrix/` | CellRanger filtered feature-barcode matrix |
| `pbmc3k.h5ad` | AnnData object with clusters and UMAP coordinates |
| `umap.png` | UMAP colored by cluster |
| `marker_genes.csv` | Top marker genes per cluster |
| `multiqc_report.html` | QC summary |
| `report.html` | Full pipeline report |
