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
- Entry point for all workflow requests; the **only** component that calls the LLM.
- LLM reasoning: parses user intent (chat) into a draft `RunConfig`, chooses stages/tools,
  asks follow-up questions. All LLM output is validated (Pydantic + DB re-checks + the
  deterministic checks in `src/agents/run_requirements.py`) before use.
- Execution: `OrchestratorAgent.execute_run(db, run_id)` loads the persisted run, re-validates
  the plan, and invokes the LangGraph `StateGraph` whose stage nodes dispatch to the
  specialist sub-agents (§3.1). No LLM call happens during execution.
- Persists state (`AnalysisRun.agent_state`) after every stage so interrupted runs resume.

### 2.2 Specialist Sub-Agents
Each sub-agent owns one phase of the pipeline:

Sub-agents are deterministic: they call tools, validate outputs, and write
`PipelineStage` / `Artifact` / result rows. They receive a typed `StageInput` built by
`src/agents/stage_inputs.py` (never by an LLM) and are invoked via
`BaseSpecialistAgent.run_stage(stage_input)`, which also records the input for the audit log.

| Agent | Responsibilities | Key Tools |
|---|---|---|
| QC Agent | Read-level QC before alignment: FastQC, MultiQC | `run_fastqc`, `run_multiqc` |
| Alignment Agent | STAR genome/transcriptome align, samtools sort/index | `run_star`, `run_samtools` |
| Alignment QC Agent | Post-alignment QC on the sorted BAM: RSeQC read distribution and strandedness (`alignment_qc` stage) | `run_rseqc`, `convert_gtf_to_bed12` |
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
- Tools run as local subprocesses; for `executor = nextflow | aws_batch` the heavy per-sample
  stages run through the Nextflow layer instead (§2.4, §3.1).

### 2.4 Nextflow Pipeline Layer
- `nextflow/main.nf` (DSL2) runs one workflow — `qc`, `alignment`, `quantification` or
  `variant_calling` — for one sample per invocation, publishing to `--output_dir`.
- Profiles: `local` (`executor = nextflow`) and `awsbatch` (`executor = aws_batch`, one Batch
  job per process, S3 work dir and outputs). Every process runs in the project's tools image
  (`NEXTFLOW_TOOLS_IMAGE`), so tool versions match local execution.
- Driven by `src/tools/nextflow/stage_runner.py`: the worker launches Nextflow, waits (polling
  for cancellation), then rebuilds the same validated ToolOutput models from the published
  files; the specialist then writes DB rows exactly as for a local run.
- Light stages (DESeq2, GSEA, rMATS, visualization, report) always run in the worker.
- Every module has a `stub:` block; CI runs the whole agent → Nextflow path with real
  Nextflow in `-stub-run` mode. Real-tool and AWS Batch validation (synthetic dataset with a known
  answer, infra scripts) is described in `docs/testing/executor_e2e.md`.

### 2.5 State & Persistence (LangGraph + SQLAlchemy)
- LangGraph `StateGraph` manages agent routing and branching.
- `AnalysisRun` entity tracks each pipeline execution lifecycle.
- Checkpointing: the merged `RunState` is written to `AnalysisRun.agent_state` after every
  stage (success or failure); `execute_run` resumes from it (§3.1).
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
    ├──[align_qc]→ Alignment QC Agent node (RSeQC)
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

### 3.1 Execution Path (non-dry-run)

```
POST /runs ─────────────┐                     (both validate user inputs first, §3.2)
chat dispatch_from_chat ┴─► AnalysisRun(pending) + RunSample rows ─► ARQ "run_pipeline"
                                                                          │
src/worker.py (arq) ─► execute_run_sync()  [src/api/background/runner.py] │
   status=running ─► OrchestratorAgent.execute_run(db, run_id) ◄──────────┘
        1. load PipelineContext (run, samples, genome)      [stage_inputs.py]
        2. re-check stage dependencies + user inputs; check executor prerequisites
           and build the Nextflow backend for nextflow / aws_batch
        3. build graph: build_pipeline_graph(stage_node_factory(runtime))
        4. graph.invoke(RunState restored from agent_state)
               router ──► <stage> node ──► router ──► … ──► END
   status=completed | failed (sanitized error_message) | cancelled (kept)
```

Each stage node (`src/agents/stage_executor.py`):
1. Checks the run was not cancelled (also before every sample/contrast).
2. Builds the specialist's typed input(s) deterministically from the DB and upstream
   `stage_outputs` (e.g. sorted BAMs from alignment, merged counts matrix for DESeq2).
3. Re-verifies the MD5 of every local upstream artifact the inputs reference (Rule 10).
   Runs the specialist once per sample (`qc`, `alignment`, `quantification`,
   `variant_calling`, `scrna_seq`), once per user contrast (`splicing`), or once per run.
   For `nextflow` / `aws_batch`, the heavy specialists' `compute` step is the Nextflow
   backend; their `persist` step (DB rows, artifacts) is unchanged.
4. Commits after each finished sample/contrast; records the validated output in
   `RunState.stage_outputs[stage]` (`{"samples": {...}}`, `{"contrasts": {...}}` or the
   `StageOutput` dict) and checkpoints to `AnalysisRun.agent_state`.
5. On failure: rolls back the failing invocation's uncommitted result rows, writes a
   `failed` `PipelineStage` audit row with its `input_params`, stores a sanitized
   `error_message`, keeps finished items as `{"…": {...}, "partial": true}`, and stops the
   graph. Re-running resumes: completed stages and finished samples/contrasts are skipped.
6. Publishes progress events (§5).

After the graph ends, the worker sets the run status and — for chat-originated runs — the
orchestrator posts a run summary to the conversation (§4). `POST /runs/{id}/retry` re-queues a
failed or cancelled run, which resumes from the checkpoint.

| Executor | Heavy per-sample stages | Outputs |
|---|---|---|
| `local` | tool subprocesses in the worker | `{OUTPUT_ROOT}/{run_id}/…` |
| `nextflow` | `nextflow -profile local` on the worker host | `{OUTPUT_ROOT}/{run_id}/…` |
| `aws_batch` | `nextflow -profile awsbatch` → AWS Batch | `s3://{S3_ARTIFACT_BUCKET}/runs/{run_id}/…`; worker downloads small result files (and BAMs only for splicing / genome tracks) |

`dry_run=true` (API request body only) runs the same graph with specialists returning the
validated fixtures in `src/tools/mock_outputs/` (`src/tools/mock_registry.py`): no input
resolution, subprocesses, or DB writes per stage.

Quantification tool selection is derived from `AnalysisRun.aligner`: `star → HTSeq`,
`salmon → Salmon`, `rsem → RSEM` (STAR then also emits a transcriptome BAM).

### 3.2 User-Decided Analysis Inputs

Some inputs change the scientific result and are therefore **never inferred** by the LLM or
by code; they must come from the user (see `api_contracts.md` → "Analysis inputs"):

| Input | Needed for | Source |
|---|---|---|
| `de_contrasts` (`numerator` = test, `denominator` = reference; any number of conditions/contrasts) | `differential_expression`, `splicing` | `POST /runs` body, or the user's chat answer |
| `read_length` | `splicing` | request body / chat answer, or identical `Sample.metadata.read_length` |
| sample `condition` | DE / splicing | `Sample` records |

`src/agents/run_requirements.py` holds one deterministic checker used by `POST /runs` (422),
the chat gateway (follow-up question) and `execute_run` (refuse to start). In chat, the
orchestrator sends the conversation history to the LLM, keeps an extracted contrast only if
both conditions exist on the selected samples **and** were named by the user, keeps a read
length only if the number appears in the user's messages, and otherwise asks a
deterministic question listing the available conditions. The created run's plan
(contrasts with fold-change direction) is echoed back to the user.

## 4. LangGraph + OpenAI Agents SDK Boundary

**LangGraph owns:**
- DAG routing and conditional edges between pipeline stages.
- `RunState` / `StageState` typed state schemas.
- Checkpointing: state snapshots persisted to `AnalysisRun.agent_state`.
- Resume logic: graph re-enters from the last completed node after a crash.

**OpenAI Agents SDK is used for:**
- Single-turn LLM completions for intent parsing (converting natural language to `RunConfig`).
- One single-turn LLM completion per finished chat-originated run (`OrchestratorAgent.summarize_run`, `src/agents/run_summary.py`): a short qualitative narrative over numbers-only excerpts of the validated outputs. Sentences containing digits are dropped; the numbers the user sees come from a deterministic **Results** list built from the tool outputs. LLM failure only removes the narrative.
- A short streamed acknowledgement when a chat run is queued (the run plan itself is appended deterministically).

Stage execution (`execute_run` and the stage nodes) makes **no** LLM calls; the worker
constructs `OrchestratorAgent(llm_client=None)` for execution and an LLM client only for the
post-run summary.

**LangGraph nodes do NOT run an Agents SDK agent loop.** Each node is a Python function that calls the SDK's `client.chat.completions.create()` directly for any LLM work, then calls deterministic tools, then returns. The Agents SDK is used as an LLM client, not as a routing framework.

**Genome resolution flow**: When a user's natural-language request references a genome (e.g. "use GRCh38"), the intent parser queries the registered `ReferenceGenome` table and includes the list of available genomes in the prompt. The LLM selects by `id`; if ambiguous, the Orchestrator returns an error asking the user to specify the exact genome name.

---

## 5. Log Aggregation for WebSocket Streaming

Real-time log streaming to `WS /ws/runs/{run_id}/logs` requires collecting logs from three sources:

- **Local subprocess tools**: stdout/stderr captured line-by-line via `subprocess.PIPE` and forwarded to a Redis pub/sub channel keyed on `run_id`.
- **Nextflow local**: Nextflow writes `.nextflow.log` and per-process logs; a file-watcher tails these and publishes new lines to the same Redis channel.
- **AWS Batch**: a background poller queries CloudWatch Logs for the job's log stream at 5-second intervals and publishes new lines.

The WebSocket handler subscribes to the Redis channel for `run_id` and forwards messages to connected clients. Log lines are stored to `PipelineStage.log_path` as flat files in parallel.

**Implemented today** (`src/agents/run_events.py`): the stage executor publishes, best-effort
(a Redis outage never fails a run):
- `logs:{run_id}` — `{ts, level, stage, agent, message}` frames at stage start/finish,
  per sample/contrast, and on failure (message sanitized).
- `conv:{conversation_id}` (chat-originated runs only) — `stage_update`
  (`running`/`completed`/`failed`), `tool_call` (`message_id` = the assistant message that
  launched the run; `summary` = numbers-only JSON excerpt of the validated output, no paths
  or prose), an `error` frame when the run fails, and finally the run summary as an assistant
  message (`token` + `done` frames).

Per-tool stdout/stderr forwarding, Nextflow log tailing and CloudWatch polling are not
implemented yet.

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
4. FastAPI enqueues arq "process_chat_message"; the worker calls
   OrchestratorAgent.dispatch_from_chat()
   a. LLM parses intent over the conversation history → draft RunConfig
   b. IDs re-validated against the DB; contrasts / read length kept only if the user
      stated them (§3.2)
   c. Missing info (samples, genome, contrasts, read length) → follow-up question
      streamed as token frames; no run created
   d. On full RunConfig: creates AnalysisRun + RunSample rows, streams an
      acknowledgement + deterministic run plan, then enqueues arq "run_pipeline"
5. FastAPI returns { message_id, run_id } to frontend
6. Frontend connects to WS /ws/conversations/{id}/stream
7. Agent events stream: tokens, then stage_update / tool_call frames from the
   stage executor (§5), and an error frame if the run fails
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
| `OrchestratorAgent.execute_run()` + `src/agents/stage_executor.py` | Execute a run: graph stage nodes dispatch to specialist sub-agents |
| `src/worker.py` | arq entry point registering `process_chat_message` and `run_pipeline` |
| FastAPI static file mount | Serve `frontend/out/` at `/app` |
