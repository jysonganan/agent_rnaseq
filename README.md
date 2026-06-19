# agent_rnaseq

Production-style computational pipeline agent for end-to-end RNA-seq analysis. Supports bulk and single-cell RNA-seq, runs locally or on AWS (S3 + Batch), and exposes results through a REST API and interactive Streamlit dashboard.

---

## Contents

- [Demo](#demo)
- [Architecture](#architecture)
- [Pipeline Stages](#pipeline-stages)
- [Installation](#installation)
- [Configuration](#configuration)
- [Quick Start — Local](#quick-start--local)
- [Quick Start — AWS S3 + Batch](#quick-start--aws-s3--batch)
- [Single-Cell RNA-seq](#single-cell-rna-seq)
- [API Reference](#api-reference)
- [Streamlit Dashboard](#streamlit-dashboard)
- [Docker](#docker)
- [Development](#development)
- [Safety Policy](#safety-policy)

---

## Demo

Run the full pipeline on synthetic example data — no bioinformatics tools or Docker required:

```bash
# Install
pip install -e ".[dev]"

# One-command demo (generates data → runs pipeline → opens Streamlit)
make demo

# Or step by step:
python data/generate_data.py        # generate synthetic FASTQ files
jupyter lab notebooks/demo.ipynb   # open and run the demo notebook
```

The notebook (`notebooks/demo.ipynb`) walks through:
1. Verifying the 8 synthetic FASTQ files in `data/` (4 samples × paired-end)
2. Initialising a SQLite database
3. Registering a reference genome, project, and samples
4. Dispatching the full pipeline via `OrchestratorAgent` and LangGraph (`dry_run=True`)
5. Generating realistic mock DE results (300 genes), GSEA pathway enrichment (25 Reactome pathways), and QC metrics
6. Interactive volcano plot, MA plot, and GSEA bubble chart inline in the notebook
7. Launching the Streamlit dashboard with the generated results

### Record a video demo

```bash
# Requires: asciinema (brew install asciinema)
make demo-record
# Output: demo/demo.cast  (+ demo/demo.gif if agg is installed)
```

See [`demo/RECORDING_GUIDE.md`](demo/RECORDING_GUIDE.md) for GIF/MP4 conversion, OBS screen recording instructions, and a suggested walkthrough script.
- [Deployment](#deployment)

---

## Architecture

```
User / API Client
      │
      ▼
┌─────────────────────────────────────────┐
│          FastAPI Gateway                │
│  REST endpoints · Auth · Job queue      │
└─────────────┬───────────────────────────┘
              │  ARQ async task queue
              ▼
┌─────────────────────────────────────────┐
│       Orchestrator Agent                │
│  OpenAI Agents SDK + LangGraph          │
│  · Parses user intent → RunConfig       │
│  · Routes to specialist sub-agents      │
│  · Maintains durable, resumable state   │
└──┬─────┬─────┬─────┬──────────────────┘
   │     │     │     │
   ▼     ▼     ▼     ▼  (10 specialist sub-agents)
  QC  Align  Quant  DE  Variant  Splicing  GSEA  scRNA  Viz  Report
   │     │     │     │
   └─────┴─────┴─────┴──→  Deterministic Tool Layer
                            (FastQC · STAR · Salmon · DESeq2 · GATK · …)
                                │
                      Pydantic schema validation
                                │
                     SQLite (dev) / PostgreSQL (prod)
                     Local disk / AWS S3
```

**Key design decision**: LLMs parse intent and route workflows. All numerical computation runs as deterministic Python/R tool calls. No LLM-generated numbers are written to the database. See [Safety Policy](#safety-policy).

### Component roles

| Component | Technology | Role |
|---|---|---|
| Orchestrator | OpenAI Agents SDK + LangGraph | Intent parsing, DAG routing, state checkpointing |
| Specialist agents | Python classes | Own one pipeline stage each; call tool functions |
| Tool layer | Python + R subprocesses | Bioinformatics computation (typed in/out, Pydantic-validated) |
| Nextflow layer | Nextflow DSL2 | Wraps multi-tool chains; local or AWS Batch executor |
| API | FastAPI | REST endpoints, WebSocket log streaming, auth |
| Database | SQLAlchemy + PostgreSQL/SQLite | Runs, samples, results, audit log |
| Dashboard | Streamlit | Interactive plots; read-only |
| AWS integration | boto3 + moto | S3 artifact store, Batch job submission |

---

## Pipeline Stages

The following stages can be included in any combination (with dependency constraints enforced):

| Stage | Tools | Outputs |
|---|---|---|
| `qc` | FastQC, MultiQC, RSeQC | QC reports, per-sample metrics |
| `alignment` | STAR (genome + transcriptome modes), samtools | Sorted/indexed BAM files |
| `quantification` | HTSeq, Salmon, RSEM | Count matrices, TPM/FPKM tables |
| `variant_calling` | GATK HaplotypeCaller | Filtered VCF files |
| `splicing` | rMATS | Differential splicing event tables |
| `differential_expression` | DESeq2 (R) | DE table: log2FC, p-value, padj |
| `gsea` | fgsea + Reactome (R) | Pathway enrichment table, NES scores |
| `visualization` | Streamlit data prep, UCSC tracks | Dashboard data, BED/bigWig tracks |
| `report` | Markdown/HTML assembly | Full analysis report |

Stage dependency rules:
- `alignment` → required by `quantification`, `variant_calling`, `splicing`
- `quantification` → required by `differential_expression`
- `differential_expression` → required by `gsea`
- `visualization` → requires at least one completed results stage

---

## Installation

### Prerequisites

- Python 3.11+
- R 4.3+ with Bioconductor packages: `DESeq2`, `fgsea`, `reactome.db`, `org.Hs.eg.db`, `org.Mm.eg.db`
- Bioinformatics tools (for local execution): STAR, samtools, FastQC, Salmon, GATK, HTSeq, RSeQC, RSEM, rMATS
- Docker + docker compose (for containerized runs)
- An OpenAI API key

All tool versions are pinned in [`docker/tool_versions.txt`](docker/tool_versions.txt). The `docker/Dockerfile.tools` image installs them automatically.

### Install Python package

```bash
git clone https://github.com/jysonganan/agent_rnaseq.git
cd agent_rnaseq
pip install -e ".[dev]"
```

### Install R dependencies

```r
install.packages("BiocManager")
BiocManager::install(c("DESeq2", "fgsea", "reactome.db", "org.Hs.eg.db", "org.Mm.eg.db"))
```

### Install bioinformatics tools (local execution)

On macOS (Homebrew):
```bash
brew install samtools fastqc
# STAR, GATK, Salmon, HTSeq — see docker/Dockerfile.tools for version-pinned install commands
```

On Linux:
```bash
# Follow the per-tool instructions in docker/Dockerfile.tools
# or pull the pre-built Docker image (see Docker section)
```

---

## Configuration

Copy the template and fill in your values:

```bash
cp .env.docker.example .env.docker   # for Docker
cp .env.docker .env                  # for local dev
```

Key variables:

```dotenv
# Required
OPENAI_API_KEY=sk-...
DATABASE_URL=sqlite:///./agent_rnaseq.db   # or postgresql://...
REDIS_URL=redis://localhost:6379/0
OUTPUT_ROOT=/tmp/agent_rnaseq              # local output directory

# AWS (required for S3/Batch workflows)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=us-east-1
AWS_S3_BUCKET=my-rnaseq-bucket
```

Credentials are always sourced from environment variables or IAM roles — never hardcoded.

---

## Quick Start — Local

### 1. Start the API server

```bash
# Option A: directly
uvicorn src.api.app:app --reload --port 8000

# Option B: via Docker (recommended — brings up all services)
docker compose -f docker/docker-compose.yml up -d
```

### 2. Create an API key

```bash
curl -s -X POST http://localhost:8000/api/v1/api-keys \
  -H "Authorization: Bearer <bootstrap-key>" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-key"}' | jq .
```

Save the `key` field — it is shown only once.

### 3. Register a reference genome

```bash
curl -s -X POST http://localhost:8000/api/v1/genomes \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "GRCh38_v43",
    "species": "homo_sapiens",
    "build": "GRCh38",
    "annotation_version": "GENCODE_v43",
    "fasta_path": "/data/genomes/GRCh38.fa",
    "gtf_path": "/data/genomes/GRCh38.gtf",
    "star_index_path": "/data/indexes/star_GRCh38",
    "salmon_index_path": "/data/indexes/salmon_GRCh38"
  }' | jq .
```

### 4. Create a project and register samples

```bash
# Create project
PROJECT_ID=$(curl -s -X POST http://localhost:8000/api/v1/projects \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{"name": "treatment_vs_control", "owner": "team_a"}' | jq -r .id)

# Register samples (paired-end FASTQ)
curl -s -X POST http://localhost:8000/api/v1/projects/$PROJECT_ID/samples \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "samples": [
      {
        "name": "ctrl_1",
        "sample_type": "bulk_rnaseq",
        "condition": "control",
        "replicate": 1,
        "fastq_r1_path": "/data/fastq/ctrl_1_R1.fastq.gz",
        "fastq_r2_path": "/data/fastq/ctrl_1_R2.fastq.gz",
        "is_paired_end": true
      },
      {
        "name": "treat_1",
        "sample_type": "bulk_rnaseq",
        "condition": "treatment",
        "replicate": 1,
        "fastq_r1_path": "/data/fastq/treat_1_R1.fastq.gz",
        "fastq_r2_path": "/data/fastq/treat_1_R2.fastq.gz",
        "is_paired_end": true
      }
    ]
  }' | jq .
```

### 5. Launch a full bulk RNA-seq pipeline run

```bash
curl -s -X POST http://localhost:8000/api/v1/runs \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "'$PROJECT_ID'",
    "genome_id": "<genome-id-from-step-3>",
    "name": "treat_vs_ctrl_v1",
    "pipeline_type": "bulk_rnaseq",
    "sample_ids": ["<ctrl-sample-id>", "<treat-sample-id>"],
    "alignment_mode": "genome",
    "aligner": "star",
    "stages": ["qc", "alignment", "quantification", "differential_expression", "gsea"],
    "de_contrasts": [
      {"name": "treatment_vs_control", "numerator": "treatment", "denominator": "control"}
    ],
    "execution": {
      "executor": "local",
      "cpus": 8,
      "memory_gb": 32
    }
  }' | jq .
```

Response:
```json
{ "run_id": "abc123", "status": "pending", "message": "Run queued" }
```

### 6. Poll status and retrieve results

```bash
# Poll run status
curl -s http://localhost:8000/api/v1/runs/abc123 \
  -H "Authorization: Bearer <api-key>" | jq '.status, .stages[].status'

# Stream live logs (WebSocket)
websocat ws://localhost:8000/ws/runs/abc123/logs

# Get DE results
curl -s "http://localhost:8000/api/v1/runs/abc123/de?contrast=treatment_vs_control&padj_cutoff=0.05" \
  -H "Authorization: Bearer <api-key>" | jq '.significant_genes'

# Get GSEA pathway enrichment
curl -s "http://localhost:8000/api/v1/runs/abc123/gsea?contrast=treatment_vs_control" \
  -H "Authorization: Bearer <api-key>" | jq '.pathways[0:5]'
```

### 7. Download artifacts

```bash
# List available artifacts
curl -s http://localhost:8000/api/v1/runs/abc123/artifacts \
  -H "Authorization: Bearer <api-key>" | jq '.artifacts[].artifact_type'

# Download DE table (returns a direct file stream in dev)
curl -s "http://localhost:8000/api/v1/runs/abc123/artifacts/<artifact-id>/download" \
  -H "Authorization: Bearer <api-key>" | jq .download_url
```

---

## Quick Start — AWS S3 + Batch

Use S3 paths for all input/output and target the `aws_batch` executor.

### 1. Upload inputs to S3

```bash
aws s3 cp ctrl_1_R1.fastq.gz s3://my-rnaseq-bucket/raw/ctrl_1_R1.fastq.gz
aws s3 cp ctrl_1_R2.fastq.gz s3://my-rnaseq-bucket/raw/ctrl_1_R2.fastq.gz
aws s3 cp treat_1_R1.fastq.gz s3://my-rnaseq-bucket/raw/treat_1_R1.fastq.gz
aws s3 cp treat_1_R2.fastq.gz s3://my-rnaseq-bucket/raw/treat_1_R2.fastq.gz
```

### 2. Register genome with S3 paths

```bash
curl -s -X POST http://localhost:8000/api/v1/genomes \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "GRCh38_v43",
    "species": "homo_sapiens",
    "build": "GRCh38",
    "annotation_version": "GENCODE_v43",
    "fasta_path": "s3://my-rnaseq-bucket/genomes/GRCh38.fa",
    "gtf_path": "s3://my-rnaseq-bucket/genomes/GRCh38.gtf",
    "star_index_path": "s3://my-rnaseq-bucket/indexes/star_GRCh38",
    "salmon_index_path": "s3://my-rnaseq-bucket/indexes/salmon_GRCh38"
  }' | jq .
```

### 3. Register samples with S3 paths

```bash
curl -s -X POST http://localhost:8000/api/v1/projects/$PROJECT_ID/samples \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "samples": [
      {
        "name": "ctrl_1",
        "sample_type": "bulk_rnaseq",
        "condition": "control",
        "replicate": 1,
        "fastq_r1_path": "s3://my-rnaseq-bucket/raw/ctrl_1_R1.fastq.gz",
        "fastq_r2_path": "s3://my-rnaseq-bucket/raw/ctrl_1_R2.fastq.gz",
        "is_paired_end": true
      }
    ]
  }' | jq .
```

### 4. Launch run on AWS Batch

```bash
curl -s -X POST http://localhost:8000/api/v1/runs \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "'$PROJECT_ID'",
    "genome_id": "<genome-id>",
    "name": "treat_vs_ctrl_batch",
    "pipeline_type": "bulk_rnaseq",
    "sample_ids": ["<ctrl-id>", "<treat-id>"],
    "stages": ["qc", "alignment", "quantification", "differential_expression", "gsea"],
    "de_contrasts": [
      {"name": "treatment_vs_control", "numerator": "treatment", "denominator": "control"}
    ],
    "execution": {
      "executor": "aws_batch",
      "cpus": 16,
      "memory_gb": 64
    }
  }' | jq .
```

Nextflow submits each stage as an AWS Batch job. Artifacts are written to `s3://my-rnaseq-bucket/outputs/<run_id>/`. Logs stream to the WebSocket endpoint via CloudWatch → Redis → client.

### 5. Run subset: QC only

```bash
curl -s -X POST http://localhost:8000/api/v1/runs \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "'$PROJECT_ID'",
    "genome_id": "<genome-id>",
    "name": "qc_check",
    "pipeline_type": "bulk_rnaseq",
    "sample_ids": ["<sample-id>"],
    "stages": ["qc"],
    "execution": {"executor": "local", "cpus": 4, "memory_gb": 8}
  }' | jq .
```

---

## Single-Cell RNA-seq

The `scrnaseq` pipeline type runs CellRanger count followed by Scanpy clustering and UMAP.

### Example

```bash
curl -s -X POST http://localhost:8000/api/v1/runs \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "'$PROJECT_ID'",
    "genome_id": "<genome-id>",
    "name": "pbmc_10x_v3",
    "pipeline_type": "scrnaseq",
    "sample_ids": ["<sample-id>"],
    "stages": ["qc", "scrnaseq", "visualization"],
    "execution": {"executor": "local", "cpus": 8, "memory_gb": 64}
  }' | jq .
```

Outputs:
- CellRanger filtered feature-barcode matrix
- Scanpy UMAP coordinates, cluster assignments, marker genes
- Cluster results stored in `scRNAClusterResult` table

### PBMC 3k example dataset

```bash
cd examples/scrnaseq
bash download_pbmc3k.sh   # downloads from 10x Genomics public data
# then open analysis.ipynb
```

> **CellRanger note**: CellRanger is licensed by 10x Genomics and cannot be bundled in the Docker image. See the comment block in [`docker/Dockerfile.tools`](docker/Dockerfile.tools) for download and installation instructions.

---

## API Reference

Base URL: `http://localhost:8000/api/v1`

All endpoints require `Authorization: Bearer <api-key>` (except `/health`).

Errors follow [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457).

### Core endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Service liveness check |
| `GET` | `/genomes` | List registered reference genomes |
| `POST` | `/genomes` | Register a reference genome |
| `GET` | `/projects` | List projects |
| `POST` | `/projects` | Create a project |
| `POST` | `/projects/{id}/samples` | Register samples |
| `GET` | `/projects/{id}/samples` | List samples in a project |
| `POST` | `/runs` | Create and launch a pipeline run |
| `GET` | `/runs` | List runs (filter by project, status) |
| `GET` | `/runs/{id}` | Run detail + stage statuses + artifacts |
| `POST` | `/runs/{id}/cancel` | Cancel a pending/running run |
| `GET` | `/runs/{id}/qc` | QC metrics for all samples |
| `GET` | `/runs/{id}/de` | DE results (filter by contrast, padj, lfc) |
| `GET` | `/runs/{id}/gsea` | GSEA pathway enrichment results |
| `GET` | `/runs/{id}/splicing` | Differential splicing events |
| `GET` | `/runs/{id}/variants` | Variant calls (filter by chrom, PASS) |
| `GET` | `/runs/{id}/artifacts` | List result artifacts |
| `GET` | `/runs/{id}/artifacts/{aid}/download` | Presigned S3 URL or file stream |
| `POST` | `/api-keys` | Issue API key (admin) |
| `GET` | `/api-keys` | List active API keys |
| `DELETE` | `/api-keys/{id}` | Revoke API key |
| `WS` | `/ws/runs/{id}/logs` | Real-time agent + tool log stream |

### Rate limits

- `POST /runs`: 10 requests/min per API key
- All other endpoints: 120 requests/min per API key

Full request/response schemas are in [`docs/specs/api_contracts.md`](docs/specs/api_contracts.md).

---

## Streamlit Dashboard

An interactive visualization dashboard is available at `http://localhost:8501` when running via Docker.

Features:
- **QC dashboard**: per-sample read quality, duplication rates, alignment rates
- **Volcano plot**: interactive DE results with gene-label search
- **MA plot**: mean-average plot for DE results
- **Pathway bubble chart**: GSEA NES scores and pathway sizes
- **Splicing heatmap**: PSI differences across conditions

The dashboard is read-only and does not have write access to the pipeline database.

---

## Docker

### Start all services

```bash
docker compose -f docker/docker-compose.yml up -d
```

Services: `api` (port 8000), `streamlit` (port 8501), `db` (PostgreSQL 16.3), `redis` (7.2), `arq-worker`.

### Stop

```bash
docker compose -f docker/docker-compose.yml down
# Remove persistent volumes too:
docker compose -f docker/docker-compose.yml down -v
```

### Build images

```bash
make docker-build
# Builds:
#   agent-rnaseq-api       — FastAPI + arq worker
#   agent-rnaseq-streamlit — Streamlit dashboard
#   agent-rnaseq-tools     — All bioinformatics tools (heavy image)
```

### Push to ECR

```bash
export REGISTRY=123456789.dkr.ecr.us-east-1.amazonaws.com
export IMAGE_TAG=v0.1.0
make docker-push
```

### Run integration tests in Docker

```bash
docker compose -f docker/docker-compose.yml \
               -f docker/docker-compose.test.yml \
               up --abort-on-container-exit --exit-code-from test-runner
```

---

## Development

### Setup

```bash
pip install -e ".[dev]"
pre-commit install
```

### Run tests

```bash
# All tests
pytest tests/ -v

# Unit tests only (no network, no Redis)
pytest tests/ -v --ignore=tests/integration

# Integration tests
pytest tests/integration/ -v
```

### Lint and format

```bash
make lint       # ruff check (no changes)
make format     # ruff format + fix
make typecheck  # mypy
```

### Project structure

```
agent_rnaseq/
├── src/
│   ├── agents/          # Orchestrator + 10 specialist sub-agents
│   │   ├── orchestrator.py
│   │   ├── router.py    # LangGraph StateGraph
│   │   ├── state.py     # RunState, StageState
│   │   └── specialists/ # QC, alignment, DE, GSEA, scRNA, …
│   ├── tools/           # Deterministic tool wrappers (typed in/out)
│   │   ├── qc/          # FastQC, MultiQC, RSeQC
│   │   ├── alignment/   # STAR, samtools
│   │   ├── de/          # DESeq2 subprocess wrapper
│   │   ├── gsea/        # fgsea/Reactome subprocess wrapper
│   │   └── …
│   ├── api/             # FastAPI routers, auth, WebSocket log streaming
│   ├── db/              # SQLAlchemy models + Alembic migrations
│   ├── schemas/         # Pydantic schemas shared across layers
│   ├── aws/             # S3FileManager, AWSBatchJobSubmitter
│   ├── streamlit/       # Visualization dashboard app
│   └── r/               # R scripts: deseq2.R, gsea.R (static, version-controlled)
├── tests/
│   ├── agents/          # Unit tests per agent
│   ├── tools/           # Unit tests per tool
│   ├── api/             # FastAPI route tests
│   └── integration/     # End-to-end pipeline tests
├── docker/
│   ├── Dockerfile.api
│   ├── Dockerfile.streamlit
│   ├── Dockerfile.tools    # All bioinformatics tools
│   ├── docker-compose.yml
│   ├── docker-compose.test.yml
│   └── tool_versions.txt   # Pinned tool versions
├── docs/
│   ├── architecture.md
│   ├── deployment.md
│   └── specs/
│       ├── api_contracts.md
│       ├── data_models.md
│       ├── tool_contracts.md
│       └── safety_policy.md
├── examples/
│   └── scrnaseq/        # PBMC 3k example dataset + Jupyter notebook
├── nextflow/            # Nextflow DSL2 pipeline configs
└── tasks/               # Implementation task files
```

---

## Safety Policy

This project enforces strict separation between LLM reasoning and numerical computation.

| Rule | Requirement |
|---|---|
| No LLM arithmetic | All fold changes, p-values, NES scores, and gene lists come from R/Python tool calls, never from LLM output |
| Schema validation | Every tool call validates both input and output with Pydantic before any DB write |
| Deterministic R scripts | DESeq2 and GSEA scripts are static files in `src/r/`; LLMs never generate R code at runtime |
| Genome selection by ID | Agents select reference genomes by database ID, not by constructing paths from LLM text |
| Parameter guardrails | `RunConfig` enforces allowed ranges: threads 1–256, alpha 0.001–0.1, lfc_threshold 0–5, etc. |
| No hardcoded credentials | AWS credentials come from environment variables or IAM roles exclusively |
| Immutable audit log | Every tool invocation is recorded in `PipelineStage`; records cannot be deleted |
| Reproducibility | Tool versions recorded at invocation time; Docker images pin all versions; random seeds recorded |
| Failure handling | Failed tool calls mark the stage `failed` and halt the run; no silent continuation |
| Output integrity | MD5 checksums computed and re-verified before downstream tool use; S3 uploads use SSE |

Full policy: [`docs/specs/safety_policy.md`](docs/specs/safety_policy.md)

---

## Deployment

See [`docs/deployment.md`](docs/deployment.md) for full production instructions covering:

- AWS ECS + Fargate service topology
- AWS Batch setup for heavy bioinformatics jobs
- Nextflow AWS Batch executor configuration
- Kubernetes alternative deployment
- Database migration workflow
- Health check endpoints
- Environment variable reference
