# agent_rnaseq

Production-style computational pipeline agent for end-to-end RNA-seq analysis. Describe your experiment in plain English; the agent selects the appropriate tools, builds a validated run configuration, and executes the pipeline. Results stream back in real time through a chat interface and an interactive dashboard.

Supports bulk and single-cell RNA-seq, runs locally or on AWS (S3 + Batch), and exposes results through a REST API, a Next.js chat UI, and an interactive Streamlit dashboard.

---

## Contents

- [Demo](#demo)
- [Architecture](#architecture)
- [Chat UI](#chat-ui)
- [Pipeline Stages](#pipeline-stages)
- [Installation](#installation)
- [Configuration](#configuration)
- [Quick Start — Chat UI](#quick-start--chat-ui)
- [Quick Start — REST API](#quick-start--rest-api)
- [Quick Start — AWS S3 + Batch](#quick-start--aws-s3--batch)
- [Single-Cell RNA-seq](#single-cell-rna-seq)
- [API Reference](#api-reference)
- [Streamlit Dashboard](#streamlit-dashboard)
- [Docker](#docker)
- [Development](#development)
- [Safety Policy](#safety-policy)
- [Deployment](#deployment)

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

The notebook walks through:
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

See [`demo/RECORDING_GUIDE.md`](demo/RECORDING_GUIDE.md) for GIF/MP4 conversion and walkthrough script.

---

## Architecture

```
Browser (Chat UI)
      │  REST + WebSocket
      ▼
┌──────────────────────────────────────────────────┐
│                 FastAPI Gateway                  │
│  /api/v1/*   /ws/runs/{id}/logs                 │
│  /conversations/*  /ws/conversations/{id}/stream│
│  /app/*  (Next.js static build — production)    │
└─────────────┬────────────────────────────────────┘
              │  ARQ async task queue (Redis)
              ▼
┌─────────────────────────────────────────┐
│           Orchestrator Agent            │
│  OpenAI Agents SDK + LangGraph          │
│  · Parses user intent → RunConfig       │
│  · Routes to specialist sub-agents      │
│  · Maintains durable, resumable state   │
│  · dispatch_from_chat() for chat msgs   │
└──┬─────┬─────┬─────┬────────────────────┘
   │     │     │     │
   ▼     ▼     ▼     ▼  (10 specialist sub-agents)
  QC  Align  Quant  DE  Variant  Splicing  GSEA  scRNA  Viz  Report
                         │
                Deterministic Tool Layer
                (FastQC · STAR · Salmon · DESeq2 · GATK · …)
                         │
               Pydantic schema validation
                         │
              SQLite (dev) / PostgreSQL (prod)
              Local disk / AWS S3
```

**Key design principle**: LLMs parse intent and route workflows. All numerical computation runs as deterministic Python/R tool calls. No LLM-generated numbers are written to the database. See [Safety Policy](#safety-policy).

### Component roles

| Component | Technology | Role |
|---|---|---|
| Chat UI | Next.js 14, TypeScript, shadcn/ui | Natural-language interface to the pipeline |
| Orchestrator | OpenAI Agents SDK + LangGraph | Intent parsing, DAG routing, state checkpointing |
| Specialist agents | Python classes | Own one pipeline stage each; call tool functions |
| Tool layer | Python + R subprocesses | Bioinformatics computation (typed in/out, Pydantic-validated) |
| Nextflow layer | Nextflow DSL2 | Wraps multi-tool chains; local or AWS Batch executor |
| API | FastAPI | REST endpoints, WebSocket streaming, auth, static file serving |
| Task queue | arq + Redis | Background processing of pipeline runs and chat messages |
| Database | SQLAlchemy + PostgreSQL/SQLite | Runs, conversations, samples, results, audit log |
| Dashboard | Streamlit | Interactive plots; read-only |
| AWS integration | boto3 | S3 artifact store, Batch job submission |

---

## Chat UI

The Chat UI is a Next.js 14 (App Router) application that lets you describe your analysis in plain English. The Orchestrator Agent interprets your intent, selects samples and a reference genome from the database, builds a validated `RunConfig`, and dispatches the pipeline. Events stream back in real time.

### Routes

| Route | Description |
|---|---|
| `/app/` or `/app/chat` | New conversation (blank thread) |
| `/app/chat/[id]` | Existing conversation — streaming agent response, tool call cards, stage progress |
| `/app/runs` | Paginated run history with status filter |
| `/app/runs/[id]` | Run detail: stage progress bar, artifact downloads, live log tail |
| `/app/browser` | Genome browser (UCSC iframe) + Streamlit embed |

### Key UI components

| Component | Purpose |
|---|---|
| `ApiKeyModal` | First-load modal for API key entry and validation |
| `AuthGuard` | Blocks all routes until a valid API key is stored in `localStorage` |
| `Sidebar` | Navigation and conversation history list |
| `ConversationThread` | Scrollable list of `UserMessage` + `AgentMessage` bubbles |
| `AgentMessage` | Markdown-rendered response via `react-markdown` (no `dangerouslySetInnerHTML`) |
| `ToolCallCard` | Inline card showing tool name, status (pending/running/completed/failed), output summary |
| `StageProgressIndicator` | Compact inline stage transition display |
| `RunStatusPanel` | Full per-stage progress bar + artifact download list |
| `StreamlitEmbed` | Sandboxed `<iframe>` pointing at the Streamlit dashboard URL |
| `GenomeBrowserEmbed` | Sandboxed `<iframe>` pointing at UCSC genome browser |

### Chat → pipeline flow

```
1. User types: "Run DE analysis on ctrl vs treatment samples"
2. POST /api/v1/conversations/{id}/messages
3. arq worker calls OrchestratorAgent.dispatch_from_chat()
   a. Queries DB for available samples and genomes (anti-hallucination)
   b. LLM parses intent → draft RunConfig (Pydantic-validated)
   c. All sample/genome IDs re-validated against DB
   d. Creates AnalysisRun, enqueues pipeline job
4. Agent response tokens stream via WS /ws/conversations/{id}/stream
5. Frontend renders streaming tokens, tool call cards, stage updates
6. On completion: artifacts available for download; Streamlit embed shows results
```

---

## Pipeline Stages

The following stages can be included in any combination (dependency constraints are enforced):

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
- Node.js 20+ (for the Chat UI)
- R 4.3+ with Bioconductor packages: `DESeq2`, `fgsea`, `reactome.db`, `org.Hs.eg.db`, `org.Mm.eg.db`
- Bioinformatics tools (for local execution): STAR, samtools, FastQC, Salmon, GATK, HTSeq, RSeQC, RSEM, rMATS
- Docker + docker compose (for containerized runs)
- Redis 7+ (for WebSocket streaming and background task queue)
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
cp .env.example .env
```

Key variables:

```dotenv
# Required
OPENAI_API_KEY=sk-...
API_KEY_BOOTSTRAP=change-me-before-use
DATABASE_URL=sqlite:///./agent_rnaseq.db   # or postgresql://...
REDIS_URL=redis://localhost:6379/0
OUTPUT_ROOT=/tmp/agent_rnaseq

# CORS — allow the Next.js dev server to call the API
# Set to "" in production (frontend served same-origin under /app)
CORS_ALLOW_ORIGINS=http://localhost:3000

# Frontend static build path (default: frontend/out)
# FRONTEND_OUT_DIR=/app/frontend/out

# AWS (required for S3/Batch workflows)
AWS_DEFAULT_REGION=us-east-1
S3_ARTIFACT_BUCKET=my-rnaseq-artifacts
AWS_BATCH_JOB_QUEUE=arn:aws:batch:us-east-1:...:job-queue/rnaseq
AWS_BATCH_JOB_DEFINITION=arn:aws:batch:us-east-1:...:job-definition/rnaseq-worker
```

AWS credentials come from environment variables or IAM roles — never hardcoded.

---

## Quick Start — Chat UI

The fastest way to run everything is via Docker Compose, which starts all services including the Next.js dev server.

```bash
# 1. Start all services
docker compose -f docker/docker-compose.yml up -d
# Services: api (8000), frontend-dev (3000), streamlit (8501),
#           db (PostgreSQL), redis, arq-worker

# 2. Create an API key
curl -s -X POST http://localhost:8000/api/v1/api-keys \
  -H "Authorization: Bearer <API_KEY_BOOTSTRAP>" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-key"}' | jq .key

# 3. Open the Chat UI
open http://localhost:3000/app
# Enter the API key in the prompt — it is stored in localStorage only
```

You can then describe your analysis in the chat box:

> *"Run QC and differential expression on my control and treatment samples using GRCh38. Compare treatment vs control."*

The agent will confirm the samples and genome, create a run, and stream progress back in the chat thread.

### Production (static build served by FastAPI)

```bash
# Build the frontend static export
make frontend-build
# Output: frontend/out/

# Start the API server (serves the built UI at /app)
uvicorn src.api.app:app --port 8000
# Open: http://localhost:8000/app
```

---

## Quick Start — REST API

If you prefer to drive the pipeline programmatically, all functionality is available via the REST API.

### 1. Create an API key

```bash
curl -s -X POST http://localhost:8000/api/v1/api-keys \
  -H "Authorization: Bearer <bootstrap-key>" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-key"}' | jq .
```

Save the `key` field — it is shown only once.

### 2. Register a reference genome

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

### 3. Create a project and register samples

```bash
PROJECT_ID=$(curl -s -X POST http://localhost:8000/api/v1/projects \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{"name": "treatment_vs_control", "owner": "team_a"}' | jq -r .id)

curl -s -X POST http://localhost:8000/api/v1/projects/$PROJECT_ID/samples \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "samples": [
      {
        "name": "ctrl_1", "sample_type": "bulk_rnaseq", "condition": "control",
        "replicate": 1, "fastq_r1_path": "/data/ctrl_1_R1.fastq.gz",
        "fastq_r2_path": "/data/ctrl_1_R2.fastq.gz", "is_paired_end": true
      },
      {
        "name": "treat_1", "sample_type": "bulk_rnaseq", "condition": "treatment",
        "replicate": 1, "fastq_r1_path": "/data/treat_1_R1.fastq.gz",
        "fastq_r2_path": "/data/treat_1_R2.fastq.gz", "is_paired_end": true
      }
    ]
  }' | jq .
```

### 4. Launch a pipeline run

```bash
curl -s -X POST http://localhost:8000/api/v1/runs \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "'$PROJECT_ID'",
    "genome_id": "<genome-id>",
    "name": "treat_vs_ctrl_v1",
    "pipeline_type": "bulk_rnaseq",
    "sample_ids": ["<ctrl-id>", "<treat-id>"],
    "alignment_mode": "genome",
    "aligner": "star",
    "stages": ["qc", "alignment", "quantification", "differential_expression", "gsea"],
    "de_contrasts": [
      {"name": "treatment_vs_control", "numerator": "treatment", "denominator": "control"}
    ],
    "execution": {"executor": "local", "cpus": 8, "memory_gb": 32}
  }' | jq .
```

### 5. Poll status and retrieve results

```bash
# Poll run status
curl -s http://localhost:8000/api/v1/runs/<run-id> \
  -H "Authorization: Bearer <api-key>" | jq '.status, .stages[].status'

# Stream live logs (WebSocket)
websocat ws://localhost:8000/api/v1/ws/runs/<run-id>/logs

# Get DE results
curl -s "http://localhost:8000/api/v1/runs/<run-id>/de?contrast=treatment_vs_control&padj_cutoff=0.05" \
  -H "Authorization: Bearer <api-key>" | jq '.significant_genes'

# Download artifact (returns presigned URL or file stream)
curl -s "http://localhost:8000/api/v1/runs/<run-id>/artifacts/<artifact-id>/download" \
  -H "Authorization: Bearer <api-key>" | jq .download_url
```

---

## Quick Start — AWS S3 + Batch

Use S3 paths for all input/output and target the `aws_batch` executor.

### 1. Upload inputs to S3

```bash
aws s3 cp ctrl_1_R1.fastq.gz s3://my-rnaseq-bucket/raw/ctrl_1_R1.fastq.gz
aws s3 cp treat_1_R1.fastq.gz s3://my-rnaseq-bucket/raw/treat_1_R1.fastq.gz
```

### 2. Register genome and samples with S3 paths

Use `s3://my-rnaseq-bucket/...` paths in the `fasta_path`, `gtf_path`, and `fastq_*_path` fields (same API calls as above).

### 3. Launch run on AWS Batch

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
    "execution": {"executor": "aws_batch", "cpus": 16, "memory_gb": 64}
  }' | jq .
```

Nextflow submits each stage as an AWS Batch job. Artifacts are written to `s3://my-rnaseq-bucket/outputs/<run_id>/`. Logs stream to the WebSocket endpoint via CloudWatch → Redis → client.

---

## Single-Cell RNA-seq

The `scrnaseq` pipeline type runs CellRanger count followed by Scanpy clustering and UMAP.

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

Outputs: CellRanger filtered feature-barcode matrix, Scanpy UMAP coordinates, cluster assignments, marker genes.

### PBMC 3k example dataset

```bash
cd examples/scrnaseq
bash download_pbmc3k.sh   # downloads from 10x Genomics public data
# then open analysis.ipynb
```

> **CellRanger note**: CellRanger is licensed by 10x Genomics and cannot be bundled in the Docker image. See [`docker/Dockerfile.tools`](docker/Dockerfile.tools) for download and installation instructions.

---

## API Reference

Base URL: `http://localhost:8000/api/v1`

All endpoints require `Authorization: Bearer <api-key>` (except `/health`). Rate limit: `POST /runs` and `POST /conversations/{id}/messages` are limited to 10 requests/min per API key. Errors follow [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457).

### Pipeline endpoints

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

### Chat / conversation endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/conversations` | Create a new conversation |
| `GET` | `/conversations` | List conversations (paginated, scoped to API key) |
| `GET` | `/conversations/{id}` | Conversation detail + message count |
| `DELETE` | `/conversations/{id}` | Soft-delete a conversation |
| `GET` | `/conversations/{id}/messages` | Fetch message history (chronological) |
| `POST` | `/conversations/{id}/messages` | Send a user message; triggers orchestrator |
| `WS` | `/ws/conversations/{id}/stream` | Stream agent token frames, tool calls, stage updates |

The WebSocket conversation stream emits JSON frames:

```json
{ "type": "token",        "payload": { "message_id": "...", "token": "..." } }
{ "type": "tool_call",    "payload": { "tool": "run_star", "status": "running" } }
{ "type": "stage_update", "payload": { "stage": "alignment", "status": "completed" } }
{ "type": "done",         "payload": { "message_id": "...", "run_id": "..." } }
{ "type": "error",        "payload": { "detail": "..." } }
```

Full request/response schemas: [`docs/specs/api_contracts.md`](docs/specs/api_contracts.md)

---

## Streamlit Dashboard

An interactive visualization dashboard is available at `http://localhost:8501` when running via Docker, and embedded in the Chat UI's `/app/browser` route.

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

Services started:

| Service | Port | Description |
|---|---|---|
| `api` | 8000 | FastAPI server (serves `/app` static build in production) |
| `frontend-dev` | 3000 | Next.js dev server (proxies `/api` to port 8000) |
| `streamlit` | 8501 | Streamlit visualization dashboard |
| `db` | 5432 | PostgreSQL 16.3 |
| `redis` | 6379 | Redis 7.2 (pub/sub + arq task queue) |
| `arq-worker` | — | Background pipeline and chat message worker |

> In development, use the Next.js dev server at **port 3000**. The static `/app` mount at port 8000 is intended for production use after `make frontend-build`.

### Stop

```bash
docker compose -f docker/docker-compose.yml down
# Remove persistent volumes too:
docker compose -f docker/docker-compose.yml down -v
```

### Build images

The API image uses a multi-stage build: Node 20 builds the frontend static export in stage 1; Python 3.11 copies the output and runs the API server in stage 2.

```bash
make docker-build
# Builds:
#   agent-rnaseq-api       — FastAPI + pre-built Next.js UI + arq worker
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

### Backend setup

```bash
pip install -e ".[dev]"
pre-commit install
```

### Frontend setup

```bash
cd frontend
npm install
npm run dev   # starts at http://localhost:3000
```

The dev server proxies `/api` and `/ws` requests to the FastAPI server at `localhost:8000`.

### Build frontend for production

```bash
make frontend-build
# Runs: cd frontend && npm ci && npm run build
# Output: frontend/out/  (served by FastAPI at /app)
```

### Run backend tests

```bash
pytest tests/ -v                         # all tests
pytest tests/ -v --ignore=tests/integration  # unit tests only
pytest tests/integration/ -v            # integration tests
```

### Run frontend tests

```bash
cd frontend
npm test                # Jest unit tests
npm run lint            # ESLint
npm run build           # TypeScript type-check + static export
```

### Lint and format (backend)

```bash
make lint       # ruff check (no changes)
make format     # ruff format + fix
make typecheck  # mypy
```

### Project structure

```
agent_rnaseq/
├── frontend/                    # Next.js 14 Chat UI (TypeScript)
│   ├── src/
│   │   ├── app/                 # App Router pages: /chat, /runs, /browser
│   │   ├── components/
│   │   │   ├── auth/            # ApiKeyModal, AuthGuard
│   │   │   ├── chat/            # ConversationThread, MessageInput, ToolCallCard, …
│   │   │   ├── layout/          # Sidebar, NavLink, AppShell
│   │   │   ├── runs/            # RunStatusPanel, RunList, ArtifactDownloadLink, …
│   │   │   ├── visualization/   # StreamlitEmbed, GenomeBrowserEmbed, VisualizationPanel
│   │   │   └── ui/              # shadcn/ui primitives
│   │   ├── hooks/               # useConversations, useRuns, useConversationStream, useRunLogStream, …
│   │   ├── lib/                 # api.ts (all fetch calls), types.ts, query-client.ts
│   │   ├── contexts/            # AuthContext
│   │   └── providers/           # ReactQueryProvider, AuthProvider
│   ├── next.config.mjs          # output: 'export', basePath: '/app'
│   └── package.json
├── src/
│   ├── agents/
│   │   ├── orchestrator.py      # OrchestratorAgent + dispatch_from_chat()
│   │   ├── router.py            # LangGraph StateGraph
│   │   ├── state.py             # RunState, StageState
│   │   └── specialists/         # QC, Alignment, DE, GSEA, scRNA, …
│   ├── tools/                   # Deterministic tool wrappers (typed in/out)
│   │   ├── qc/                  # FastQC, MultiQC, RSeQC
│   │   ├── alignment/           # STAR, samtools
│   │   ├── de/                  # DESeq2 subprocess wrapper
│   │   ├── gsea/                # fgsea/Reactome subprocess wrapper
│   │   └── …
│   ├── api/
│   │   ├── app.py               # FastAPI factory (CORS, static mount, all routers)
│   │   ├── routers/             # conversations, runs, genomes, projects, …
│   │   └── websocket/           # conversation_stream.py, ws/logs.py
│   ├── workers/
│   │   └── tasks.py             # process_chat_message arq task
│   ├── db/                      # SQLAlchemy models + migrations
│   ├── schemas/                 # Pydantic schemas shared across layers
│   ├── aws/                     # S3FileManager, AWSBatchJobSubmitter
│   ├── streamlit/               # Visualization dashboard app
│   └── r/                       # R scripts: deseq2.R, gsea.R (static, version-controlled)
├── tests/
│   ├── agents/                  # Unit tests per agent
│   ├── tools/                   # Unit tests per tool
│   ├── api/                     # FastAPI route tests (including conversations)
│   └── integration/             # End-to-end pipeline tests
├── docker/
│   ├── Dockerfile.api           # Multi-stage: node-build + python-runtime
│   ├── Dockerfile.streamlit
│   ├── Dockerfile.tools
│   ├── docker-compose.yml       # Includes frontend-dev service
│   └── tool_versions.txt
├── docs/
│   ├── architecture.md
│   └── specs/
│       ├── api_contracts.md
│       ├── data_models.md
│       ├── tool_contracts.md
│       └── safety_policy.md
├── nextflow/                    # Nextflow DSL2 pipeline configs
├── tasks/                       # Backend implementation task files
├── tasks_frontend/              # Frontend implementation task files
├── Makefile
└── .env.example
```

---

## Safety Policy

This project enforces strict separation between LLM reasoning and numerical computation, and between user input and privileged system state.

| Rule | Requirement |
|---|---|
| No LLM arithmetic | All fold changes, p-values, NES scores, and gene lists come from R/Python tool calls — never from LLM output |
| Schema validation | Every tool call validates both input and output with Pydantic before any DB write |
| Deterministic R scripts | DESeq2 and GSEA scripts are static files in `src/r/`; LLMs never generate R code at runtime |
| Genome and sample selection | Agents select resources by database ID only; LLMs may not invent or infer UUIDs from free text |
| Parameter guardrails | `RunConfig` enforces allowed ranges: threads 1–256, alpha 0.001–0.1, lfc_threshold 0–5, etc. |
| No hardcoded credentials | AWS credentials come from environment variables or IAM roles exclusively |
| Immutable audit log | Every tool invocation is recorded in `PipelineStage`; records cannot be deleted |
| Reproducibility | Tool versions recorded at invocation time; Docker images pin all versions; random seeds recorded |
| Failure handling | Failed tool calls mark the stage `failed` and halt the run; no silent continuation |
| Output integrity | MD5 checksums computed and re-verified before downstream use; S3 uploads use SSE |
| Frontend API key | API key stored only in `localStorage['rnaseq_api_key']`; never in URL params, cookies, or session storage |
| No `dangerouslySetInnerHTML` | All user and agent content rendered through `react-markdown` with a restricted element allowlist |
| iframe sandboxing | Streamlit and UCSC browser iframes have explicit `sandbox` attributes; no `allow-top-navigation` |
| Content sanitization | Agent responses stripped of file paths, AWS credential patterns, and tracebacks before DB write |

Full policy: [`docs/specs/safety_policy.md`](docs/specs/safety_policy.md)

---

## Deployment

See [`docs/deployment.md`](docs/deployment.md) for full production instructions covering:

- AWS ECS + Fargate service topology
- AWS Batch setup for heavy bioinformatics jobs
- Nextflow AWS Batch executor configuration
- Kubernetes alternative deployment
- Database migration workflow
- Environment variable reference

### Production quick reference

In production, set:

```dotenv
APP_ENV=production
DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/agent_rnaseq
CORS_ALLOW_ORIGINS=          # empty — frontend served same-origin at /app
FRONTEND_OUT_DIR=/app/frontend/out
```

The single `agent-rnaseq-api` Docker image serves both the FastAPI backend (`/api/v1/*`) and the pre-built Next.js frontend (`/app/*`) from the same origin, eliminating cross-origin requests in production.
