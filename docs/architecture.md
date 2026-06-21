# Architecture: agent_rnaseq

## 1. High-Level Architecture

```
User / API Client
      │
      ▼
┌─────────────────────────────────────────┐
│          FastAPI Gateway                │
│  (REST endpoints, auth, job management) │
└─────────────┬───────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│       Orchestrator Agent                │
│  (OpenAI Agents SDK + LangGraph)        │
│  - Parses user intent                   │
│  - Selects sub-agents & routing         │
│  - Maintains durable workflow state     │
└──┬──────────┬──────────┬───────────────┘
   │          │          │
   ▼          ▼          ▼
[QC Agent] [Align Agent] [Quant Agent]
   │          │          │
   ▼          ▼          ▼
[Variant   [DE Agent]  [scRNA Agent]
 Agent]         │
           [GSEA Agent]
                │
           [Viz Agent]
                │
           [Report Agent]

All agents → Deterministic Tool Layer → Bioinformatics Binaries / R Scripts
All agents → LangGraph State Store → SQLite (dev) / PostgreSQL (prod)
All agents ← Tool results validated by Pydantic schemas
```

## 2. Major Components

### 2.1 Orchestrator Agent
- Entry point for all workflow requests.
- Uses LangGraph `StateGraph` for routing and durable state.
- Decomposes user intent into a directed acyclic graph of sub-agent tasks.
- Maintains run context: sample manifest, genome config, tool parameters.
- Persists state so interrupted runs can resume.

### 2.2 Specialist Sub-Agents
Each sub-agent owns one phase of the pipeline:

| Agent | Responsibilities | Key Tools |
|---|---|---|
| QC Agent | FastQC, MultiQC, RSeQC | `run_fastqc`, `run_multiqc`, `run_rseqc` |
| Alignment Agent | STAR genome/transcriptome align, samtools sort/index | `run_star`, `run_samtools` |
| Quantification Agent | HTSeq counts, Salmon quant, RSEM | `run_htseq`, `run_salmon`, `run_rsem` |
| Variant Agent | GATK HaplotypeCaller, VCF filtering | `run_gatk`, `run_vcf_filter` |
| Splicing Agent | rMATS / LeafCutter splicing analysis | `run_rmats` |
| DE Agent | DESeq2 differential expression | `run_deseq2` |
| GSEA Agent | Reactome pathway enrichment | `run_reactome_gsea` |
| scRNA Agent | CellRanger count, Seurat/Scanpy | `run_cellranger`, `run_scanpy` |
| Viz Agent | Streamlit app data prep, UCSC track generation | `prepare_streamlit_data`, `generate_ucsc_tracks` |
| Report Agent | Markdown/HTML report assembly | `compile_report` |

### 2.3 Deterministic Tool Layer
- All bioinformatics computations are Python or R functions, not LLM calls.
- Each tool is a typed Python function: `input: ToolInput → output: ToolOutput`.
- Inputs and outputs validated with Pydantic before/after execution.
- Tool functions can dispatch to: local subprocess, Nextflow pipeline, or AWS Batch job.

### 2.4 Nextflow Pipeline Layer
- Nextflow DSL2 workflows wrap multi-step tool chains.
- Used for compute-heavy phases: alignment, quantification, variant calling.
- Supports local executor and AWS Batch executor transparently.
- FASTQ files read from local disk or S3.

### 2.5 State & Persistence (LangGraph + SQLAlchemy)
- LangGraph `StateGraph` manages agent routing and branching.
- `AnalysisRun` entity tracks each pipeline execution lifecycle.
- Checkpointing: LangGraph state snapshots stored in DB so runs survive crashes.
- File artifacts stored on local disk or S3; paths recorded in DB.

### 2.6 FastAPI Service
- `POST /runs` — create and launch a new analysis run.
- `GET /runs/{run_id}` — poll run status and retrieve results.
- `GET /runs/{run_id}/artifacts/{artifact_type}` — download result files.
- `POST /runs/{run_id}/cancel` — cancel a run.
- `GET /genomes` — list configured reference genomes.
- WebSocket endpoint for streaming agent log messages.

### 2.7 Streamlit Visualization App
- Reads processed result files (DESeq2 tables, GSEA output, QC metrics).
- Interactive: volcano plots, MA plots, pathway bubble charts, QC dashboards.
- Served as a standalone Docker container.
- Does NOT have write access to the pipeline database.

### 2.8 AWS Integration
- S3: input FASTQ files, reference genomes, output artifacts.
- Batch: compute environments for heavy jobs (alignment, variant calling).
- Credentials via IAM roles / environment variables; never hardcoded.
- `AWSBatchJobSubmitter` wraps Nextflow's Batch executor config.

## 3. Routing Agent Design

```
User request
    │
    ▼
Intent Parser (LLM) → RunConfig (Pydantic)
    │
    ▼
Workflow Planner (LangGraph node)
    │  Outputs: ordered list of pipeline stages
    ▼
Stage Router (LangGraph conditional edges)
    │
    ├──[qc]──────→ QC Agent node
    ├──[align]───→ Alignment Agent node
    ├──[quant]───→ Quantification Agent node
    ├──[variant]─→ Variant Agent node
    ├──[splicing]→ Splicing Agent node
    ├──[de]──────→ DE Agent node
    ├──[gsea]────→ GSEA Agent node
    ├──[scrnaseq]→ scRNA Agent node
    ├──[viz]─────→ Viz Agent node
    └──[report]──→ Report Agent node
                        │
                        ▼
                   END (run complete)
```

Each node:
1. Receives typed `StageInput` from graph state.
2. Calls deterministic tools.
3. Validates tool outputs.
4. Writes results to DB + artifact store.
5. Updates graph state with `StageOutput`.
6. Returns control to router.

## 4. LangGraph + OpenAI Agents SDK Boundary

**LangGraph owns:**
- DAG routing and conditional edges between pipeline stages.
- `RunState` / `StageState` typed state schemas.
- Checkpointing: state snapshots persisted to `AnalysisRun.agent_state`.
- Resume logic: graph re-enters from the last completed node after a crash.

**OpenAI Agents SDK is used for:**
- Single-turn LLM completions for intent parsing (converting natural language to `RunConfig`).
- Single-turn LLM completions for stage summaries (converting `StageOutput` to human-readable narrative).

**LangGraph nodes do NOT run an Agents SDK agent loop.** Each node is a Python function that calls the SDK's `client.chat.completions.create()` directly for any LLM work, then calls deterministic tools, then returns. The Agents SDK is used as an LLM client, not as a routing framework.

**Genome resolution flow**: When a user's natural-language request references a genome (e.g. "use GRCh38"), the intent parser queries the registered `ReferenceGenome` table and includes the list of available genomes in the prompt. The LLM selects by `id`; if ambiguous, the Orchestrator returns an error asking the user to specify the exact genome name.

---

## 5. Log Aggregation for WebSocket Streaming

Real-time log streaming to `WS /ws/runs/{run_id}/logs` requires collecting logs from three sources:

- **Local subprocess tools**: stdout/stderr captured line-by-line via `subprocess.PIPE` and forwarded to a Redis pub/sub channel keyed on `run_id`.
- **Nextflow local**: Nextflow writes `.nextflow.log` and per-process logs; a file-watcher tails these and publishes new lines to the same Redis channel.
- **AWS Batch**: a background poller queries CloudWatch Logs for the job's log stream at 5-second intervals and publishes new lines.

The WebSocket handler subscribes to the Redis channel for `run_id` and forwards messages to connected clients. Log lines are stored to `PipelineStage.log_path` as flat files in parallel.

---

## 6. Data Flow

```
FASTQ (S3 / local)
    → QC (FastQC reports)
    → Alignment (BAM files: STAR genome / STAR transcriptome)
    → Quantification (count matrices: HTSeq / Salmon / RSEM)
    → Variant Calling (VCF: GATK)
    → Splicing Analysis (splicing events: rMATS)
    → Differential Expression (DE table: DESeq2)
    → GSEA (pathway enrichment: Reactome)
    → Visualization (Streamlit app / UCSC tracks)
    → Report (HTML / Markdown)
```

## 7. Genome & Reference Configuration
- Genomes registered in DB: `ReferenceGenome` table.
- Fields: species, build (GRCh38, mm10, etc.), FASTA path, GTF path, STAR index path, Salmon index path.
- Agents select genome from run config; never from LLM free text.
- See "Genome resolution flow" in Section 4 for how natural-language genome references are resolved.
- Supports multi-genome runs (e.g. hybrid host+pathogen).

## 8. Single-Cell Support
- CellRanger wraps 10x Genomics data preprocessing.
- Output: filtered feature-barcode matrix.
- Scanpy / Seurat pipeline: clustering, UMAP, marker genes.
- Results stored in `scRNAClusterResult` table (per `data_models.md`).
- Example dataset in `examples/scrnaseq/`.

## 9. Deployment Topology

```
dev:   docker-compose (API + SQLite + Streamlit + local Nextflow)
       + Next.js dev server (localhost:3000, proxies to localhost:8000)
prod:  Kubernetes or ECS (API + PostgreSQL + Streamlit)
       + FastAPI serves Next.js static build under /app
       + AWS Batch (Nextflow pipelines)
       + S3 (artifacts)
```

---

## 10. Frontend Architecture

### 10.1 Overview

The Chat UI is a Next.js 14 (App Router) TypeScript application that provides a natural-language interface to the RNA-seq pipeline. Users describe their analysis in plain English; the Orchestrator Agent interprets the intent, builds a `RunConfig`, and dispatches the pipeline. Results stream back in real time via WebSocket.

```
Browser (Next.js App)
      │
      │  REST (React Query)      WebSocket
      ▼                          ▼
┌──────────────────────────────────────────────┐
│              FastAPI Gateway                 │
│  /api/v1/*   /ws/runs/{id}/logs              │
│  /conversations/*  /ws/conversations/{id}/… │
└──────────┬──────────────────────────────────┘
           │
           ▼
    OrchestratorAgent
    (OpenAI Agents SDK + LangGraph)
           │
    … existing pipeline agents …
```

FastAPI serves the compiled Next.js static build under `/app` in production. In development the Next.js dev server runs on port 3000 and proxies `/api` and `/ws` to the FastAPI server on port 8000.

---

### 10.2 Next.js App Router Structure

| Route | View |
|---|---|
| `/` | Redirects to `/chat` |
| `/chat` | New conversation (blank thread) |
| `/chat/[conversation_id]` | Existing conversation thread |
| `/runs` | Paginated run history list |
| `/runs/[run_id]` | Run detail: stage progress + artifacts |
| `/browser` | Genome browser (UCSC iframe) + Streamlit embed |

---

### 10.3 Major UI Components

| Component | Purpose |
|---|---|
| `AuthGuard` | Blocks all routes until a valid API key is stored |
| `ApiKeyModal` | First-load modal for API key entry and validation |
| `Sidebar` | Navigation: Chat, Runs, Browser; conversation history list |
| `ConversationThread` | Scrollable list of `UserMessage` + `AgentMessage` bubbles |
| `MessageInput` | Textarea + submit button; disabled while agent is responding |
| `AgentMessage` | Markdown-rendered agent response via `react-markdown` |
| `ToolCallCard` | Inline card: tool name, running/completed/failed status, output summary |
| `StageProgressIndicator` | Compact inline indicator for stage transitions |
| `RunStatusPanel` | Full stage-by-stage progress bar + artifact download list |
| `ArtifactDownloadLink` | Calls `/artifacts/{id}/download`, opens presigned URL |
| `RunList` / `RunListItem` | History view rows with status badge |
| `StreamlitEmbed` | `<iframe>` pointing at configurable Streamlit URL |
| `GenomeBrowserEmbed` | `<iframe>` pointing at UCSC genome browser |

---

### 10.4 API Client Layer

All server communication goes through `frontend/src/lib/api.ts`:

```
api.ts
  ├── apiFetch(path, options)   — injects Authorization header, maps HTTP errors to ApiError
  ├── conversationsApi          — CRUD for /conversations + POST message
  ├── runsApi                   — GET /runs, GET /runs/{id}, POST /runs/{id}/cancel
  └── artifactsApi              — GET /runs/{id}/artifacts, GET download URL
```

React Query `QueryClient` (singleton in `query-client.ts`) caches and invalidates:
- `['conversations']` — invalidated on new conversation
- `['conversation', id]` — invalidated on new message
- `['runs']` — polled every 5 s while any run is `pending` or `running`
- `['run', id]` — polled every 3 s while run is not terminal

---

### 10.5 WebSocket Streaming

Two WebSocket hooks:

**`useRunLogStream(run_id)`**
- Connects to `WS /ws/runs/{run_id}/logs`
- Parses `{ ts, level, stage, agent, message }` frames
- Appends to a local log buffer displayed in `RunStatusPanel`

**`useConversationStream(conversation_id)`**
- Connects to `WS /ws/conversations/{conversation_id}/stream`
- Parses frames: `{ type: "token" | "tool_call" | "stage_update" | "done", payload }`
- `token` frames accumulate into the current `AgentMessage` (streaming effect)
- `tool_call` frames create / update `ToolCallCard` components
- `stage_update` frames update `StageProgressIndicator`
- Both hooks reconnect with exponential back-off (max 3 retries, then show error)

---

### 10.6 Authentication Flow

```
1. App load → AuthContext reads localStorage['rnaseq_api_key']
2. Key absent → render ApiKeyModal (blocks all other routes)
3. User submits key → GET /health with Authorization: Bearer <key>
4. 200 → store in localStorage, dismiss modal, render app
5. 401 → show error "Invalid API key", clear stored value
6. Key present → all apiFetch calls inject header automatically
7. Any 401 from API → clear key, show ApiKeyModal
```

The raw key lives only in localStorage and in HTTP request headers. It is never included in URL query params, POST bodies, or DB records.

---

### 10.7 Chat → Pipeline Dispatch Flow

```
1. User types: "Run DE analysis on ctrl vs treatment samples"
2. POST /conversations/{id}/messages  { role: "user", content: "..." }
3. FastAPI creates ChatMessage(role=user)
4. FastAPI calls OrchestratorAgent.dispatch_from_chat(message, conversation_id)
   a. LLM parses intent → draft RunConfig (Pydantic-validated)
   b. Prompts for any missing info (genome, samples) as follow-up agent messages
   c. On full RunConfig: creates AnalysisRun, enqueues job via arq
   d. Returns run_id
5. FastAPI returns { message_id, run_id } to frontend
6. Frontend connects to WS /ws/conversations/{id}/stream
7. Agent events stream: thinking tokens, tool call cards, stage updates
8. On run completion: Streamlit data files available; StreamlitEmbed shows results
```

---

### 10.8 New Backend Components Required

| Component | Description |
|---|---|
| `Conversation` DB model | Stores chat conversation metadata |
| `ChatMessage` DB model | Individual user / assistant / tool messages |
| `POST /conversations` | Create a conversation |
| `GET /conversations` | List conversations (paginated) |
| `POST /conversations/{id}/messages` | Send a message, trigger agent |
| `GET /conversations/{id}/messages` | Fetch message history |
| `WS /ws/conversations/{id}/stream` | Stream agent response tokens + events |
| `OrchestratorAgent.dispatch_from_chat()` | Parse intent + create AnalysisRun |
| FastAPI static file mount | Serve `frontend/out/` at `/app` |
