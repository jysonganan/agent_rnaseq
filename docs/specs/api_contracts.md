# API Contracts Specification

## Runtime: FastAPI | Auth: Bearer token (API key) | Format: JSON

Base URL: `http://localhost:8000/api/v1` (dev) | `https://<host>/api/v1` (prod)

All request/response bodies use `application/json`.
All timestamps are ISO 8601 UTC.
All IDs are UUID v4 strings.
Errors follow RFC 9457 Problem Details.

---

## Authentication

All endpoints (except `/health`) require:
```
Authorization: Bearer <api_key>
```

---

## Error Schema

```json
{
  "type": "https://agent-rnaseq.io/errors/<slug>",
  "title": "Human-readable title",
  "status": 422,
  "detail": "Specific reason",
  "instance": "/api/v1/runs/abc123"
}
```

---

## Endpoints

### Health

#### `GET /health`
Returns service liveness.

**Response 200**
```json
{ "status": "ok", "version": "0.1.0" }
```

---

### Reference Genomes

#### `GET /genomes`
List all registered reference genomes.

**Query params**: `limit` (default 20), `offset` (default 0)

**Response 200**
```json
{
  "genomes": [
    {
      "id": "uuid",
      "name": "GRCh38_v43",
      "species": "homo_sapiens",
      "build": "GRCh38",
      "annotation_version": "GENCODE_v43",
      "fasta_path": "s3://bucket/genomes/GRCh38.fa",
      "has_star_index": true,
      "has_salmon_index": true,
      "has_rsem_index": false,
      "created_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

#### `POST /genomes`
Register a new reference genome.

**Request body**
```json
{
  "name": "GRCh38_v43",
  "species": "homo_sapiens",
  "build": "GRCh38",
  "annotation_version": "GENCODE_v43",
  "fasta_path": "s3://bucket/genomes/GRCh38.fa",
  "gtf_path": "s3://bucket/genomes/GRCh38.gtf",
  "star_index_path": "s3://bucket/indexes/star_GRCh38",
  "salmon_index_path": "s3://bucket/indexes/salmon_GRCh38"
}
```

**Response 201** — returns created genome object.

---

### Projects

#### `GET /projects`
**Query params**: `limit` (default 20), `offset` (default 0)

**Response 200**
```json
{
  "total": 10,
  "projects": [{ "id": "uuid", "name": "...", "owner": "...", "created_at": "..." }]
}
```

#### `GET /projects/{project_id}`
**Response 200** — full project object with `id`, `name`, `description`, `owner`, `created_at`, `updated_at`.
**Response 404** — RFC 9457 error if project not found.

#### `POST /projects`
**Request body**
```json
{ "name": "My RNA-seq Experiment", "description": "Optional", "owner": "team_a" }
```
**Response 201** — returns created project.

---

### Samples

#### `POST /projects/{project_id}/samples`
Register one or more samples.

**Request body**
```json
{
  "samples": [
    {
      "name": "sample_ctrl_1",
      "sample_type": "bulk_rnaseq",
      "condition": "control",
      "replicate": 1,
      "fastq_r1_path": "s3://bucket/raw/ctrl_1_R1.fastq.gz",
      "fastq_r2_path": "s3://bucket/raw/ctrl_1_R2.fastq.gz",
      "is_paired_end": true,
      "metadata": {}
    }
  ]
}
```
**Response 201**
```json
{ "created": 1, "sample_ids": ["uuid"] }
```

#### `GET /projects/{project_id}/samples`
**Response 200** — array of sample objects.

#### `GET /samples/{sample_id}`
**Response 200** — single sample object.
**Response 404** — RFC 9457 error if not found.

---

### Analysis Runs

#### `POST /runs`
Create and launch a new analysis run.

**Request body**
```json
{
  "project_id": "uuid",
  "genome_id": "uuid",
  "name": "ctrl_vs_treatment_v1",
  "pipeline_type": "bulk_rnaseq",
  "sample_ids": ["uuid1", "uuid2"],
  "alignment_mode": "genome",
  "aligner": "star",
  "stages": ["qc", "alignment", "quantification", "differential_expression", "gsea", "report"],
  "de_contrasts": [
    { "name": "treatment_vs_control", "numerator": "treatment", "denominator": "control" }
  ],
  "execution": {
    "executor": "local",
    "cpus": 8,
    "memory_gb": 32
  }
}
```

**Response 202**
```json
{
  "run_id": "uuid",
  "status": "pending",
  "message": "Run queued"
}
```

#### `GET /runs`
List runs, optionally filtered.

**Query params**: `project_id`, `status`, `limit` (default 20), `offset` (default 0)

**Response 200**
```json
{
  "total": 42,
  "runs": [
    {
      "id": "uuid",
      "name": "ctrl_vs_treatment_v1",
      "status": "running",
      "pipeline_type": "bulk_rnaseq",
      "created_at": "...",
      "started_at": "...",
      "completed_at": null
    }
  ]
}
```

#### `GET /runs/{run_id}`
Get full run detail including stage statuses.

**Response 200**
```json
{
  "id": "uuid",
  "name": "...",
  "status": "completed",
  "pipeline_type": "bulk_rnaseq",
  "genome": { "id": "uuid", "name": "GRCh38_v43" },
  "conversation_id": "uuid or null",
  "triggering_message_id": "uuid or null",
  "stages": [
    {
      "id": "uuid",
      "stage_name": "qc",
      "status": "completed",
      "tool_name": "fastqc",
      "started_at": "...",
      "completed_at": "..."
    }
  ],
  "artifacts": [
    {
      "id": "uuid",
      "artifact_type": "de_table",
      "path": "s3://bucket/runs/uuid/de_table.csv",
      "file_size_bytes": 1024000
    }
  ],
  "created_at": "...",
  "started_at": "...",
  "completed_at": "..."
}
```

#### `POST /runs/{run_id}/cancel`
Cancel a running or pending run.

**Response 200**
```json
{ "run_id": "uuid", "status": "cancelled" }
```

---

### Artifacts

#### `GET /runs/{run_id}/artifacts`
List all artifacts for a run.

**Query params**: `artifact_type` (optional filter)

**Response 200**
```json
{
  "artifacts": [
    {
      "id": "uuid",
      "artifact_type": "de_table",
      "path": "s3://bucket/...",
      "file_size_bytes": 1024000,
      "created_at": "..."
    }
  ]
}
```

#### `GET /runs/{run_id}/artifacts/{artifact_id}/download`
Returns a presigned S3 URL (prod) or direct file stream (dev).

**Response 200**
```json
{ "download_url": "https://...", "expires_in_seconds": 3600 }
```

---

### QC Metrics

#### `GET /runs/{run_id}/qc`
Get parsed QC metrics for all samples in a run.

**Response 200**
```json
{
  "run_id": "uuid",
  "metrics": [
    {
      "sample_id": "uuid",
      "sample_name": "ctrl_1",
      "metrics": {
        "total_reads": 45000000,
        "pct_duplication": 12.3,
        "median_insert_size": 185,
        "pct_aligned": 94.2,
        "rseqc_read_distribution": {}
      }
    }
  ]
}
```

---

### DE Results

#### `GET /runs/{run_id}/de`
Get differential expression results.

**Query params**: `contrast` (required), `padj_cutoff` (default 0.05), `lfc_cutoff` (default 1.0), `limit` (default 500)

**Response 200**
```json
{
  "run_id": "uuid",
  "contrast": "treatment_vs_control",
  "total_genes": 18000,
  "significant_genes": 423,
  "results": [
    {
      "gene_id": "ENSG00000...",
      "gene_name": "TP53",
      "basemean": 1200.5,
      "log2_fold_change": 2.3,
      "pvalue": 1.2e-8,
      "padj": 3.4e-6
    }
  ]
}
```

---

### GSEA Results

#### `GET /runs/{run_id}/gsea`
Get pathway enrichment results.

**Query params**: `contrast` (required), `padj_cutoff` (default 0.05)

**Response 200**
```json
{
  "run_id": "uuid",
  "contrast": "treatment_vs_control",
  "pathways": [
    {
      "pathway_id": "R-HSA-109581",
      "pathway_name": "Apoptosis",
      "nes": 1.85,
      "pvalue": 0.001,
      "padj": 0.012,
      "leading_edge_genes": ["TP53", "BAX", "BCL2"]
    }
  ]
}
```

---

### Splicing Results

#### `GET /runs/{run_id}/splicing`
Get differential splicing results.

**Query params**: `contrast` (required), `event_type` (optional: SE/A5SS/A3SS/MXE/RI), `fdr_cutoff` (default 0.05), `limit` (default 500)

**Response 200**
```json
{
  "run_id": "uuid",
  "contrast": "treatment_vs_control",
  "total_events": 312,
  "results": [
    {
      "gene_id": "ENSG00000...",
      "gene_name": "PTBP1",
      "event_type": "SE",
      "inclusion_level_diff": -0.35,
      "pvalue": 1.1e-5,
      "fdr": 0.003
    }
  ]
}
```

---

### Variant Results

#### `GET /runs/{run_id}/variants`
Get variant calls for a run.

**Query params**: `sample_id` (optional), `chrom` (optional), `filter` (optional: PASS/all), `limit` (default 500), `offset` (default 0)

**Response 200**
```json
{
  "run_id": "uuid",
  "total": 5421,
  "variants": [
    {
      "id": "uuid",
      "sample_id": "uuid",
      "chrom": "chr17",
      "pos": 7674220,
      "ref": "C",
      "alt": "T",
      "qual": 312.5,
      "filter": "PASS"
    }
  ]
}
```

---

### API Key Management

#### `POST /api-keys`
Issue a new API key. Admin-only endpoint (requires a bootstrap key or admin scope).

**Request body**
```json
{ "name": "ci-pipeline-key", "expires_at": "2027-01-01T00:00:00Z" }
```

**Response 201**
```json
{
  "id": "uuid",
  "name": "ci-pipeline-key",
  "key": "<raw-key-shown-once>",
  "expires_at": "2027-01-01T00:00:00Z"
}
```
The raw key is returned only at creation time and never again.

#### `GET /api-keys`
List all active (non-revoked) API keys. Returns metadata only — never the raw key or hash.

**Response 200**
```json
{
  "keys": [
    { "id": "uuid", "name": "ci-pipeline-key", "created_at": "...", "expires_at": "..." }
  ]
}
```

#### `DELETE /api-keys/{key_id}`
Revoke an API key immediately.

**Response 200**
```json
{ "id": "uuid", "revoked_at": "2026-06-10T12:00:00Z" }
```

---

### WebSocket: Run Log Stream

#### `WS /ws/runs/{run_id}/logs`
Streams agent log messages in real time.

**Authentication**: send API key as query param `?api_key=<key>` (WebSocket does not support custom headers in browsers). The handler validates the key against the `APIKey` table and verifies the run belongs to that key before subscribing to the Redis channel.

**Message format**
```json
{
  "ts": "2026-01-01T12:00:00Z",
  "level": "info",
  "stage": "alignment",
  "agent": "alignment_agent",
  "message": "STAR alignment started for sample ctrl_1"
}
```

---

### Conversations (Chat UI)

#### `POST /conversations`
Create a new conversation thread.

**Request body**
```json
{ "title": "Optional override title" }
```

**Response 201**
```json
{ "id": "uuid", "title": "New conversation", "created_at": "..." }
```

#### `GET /conversations`
List conversations for the authenticated API key.

**Query params**: `limit` (default 20), `offset` (default 0)

**Response 200**
```json
{
  "total": 5,
  "conversations": [
    { "id": "uuid", "title": "DE analysis ctrl vs treatment", "updated_at": "..." }
  ]
}
```

#### `GET /conversations/{conversation_id}`
Get conversation metadata.

**Response 200**
```json
{ "id": "uuid", "title": "...", "created_at": "...", "updated_at": "..." }
```
**Response 404** — RFC 9457 if not found or not owned by caller's API key.

#### `GET /conversations/{conversation_id}/messages`
Get full message history for a conversation.

**Query params**: `limit` (default 100), `offset` (default 0)

**Response 200**
```json
{
  "total": 12,
  "messages": [
    {
      "id": "uuid",
      "role": "user",
      "content": "Run DE analysis comparing treatment vs control",
      "run_id": null,
      "tool_name": null,
      "tool_status": null,
      "created_at": "..."
    },
    {
      "id": "uuid",
      "role": "assistant",
      "content": "I'll set up a bulk RNA-seq differential expression run ...",
      "run_id": "uuid",
      "tool_name": null,
      "tool_status": null,
      "created_at": "..."
    },
    {
      "id": "uuid",
      "role": "tool",
      "content": "{\"tool\": \"run_deseq2\", \"status\": \"completed\", \"significant_genes\": 423}",
      "run_id": "uuid",
      "tool_name": "run_deseq2",
      "tool_status": "completed",
      "created_at": "..."
    }
  ]
}
```

#### `DELETE /conversations/{conversation_id}`
Soft-delete a conversation (sets `deleted_at`; excludes it from `GET /conversations`). Cascades to mark all `ChatMessage` records as deleted.

**Response 200**
```json
{ "id": "uuid", "deleted_at": "2026-06-20T10:00:00Z" }
```
**Response 404** — RFC 9457 if not found or not owned by caller.

#### `POST /conversations/{conversation_id}/messages`
Send a user message and trigger agent processing.

**Request body**
```json
{ "content": "Run DE analysis comparing treatment vs control" }
```
`content` is required and must be 1–4000 characters. Returns 422 if blank or exceeds limit.

**Response 202**
```json
{
  "message_id": "uuid",
  "run_id": "uuid",
  "status": "processing"
}
```

The endpoint:
1. Validates `content` length (1–4000 chars); returns 422 on violation.
2. Persists a `ChatMessage` with `role=user`.
3. Updates `Conversation.title` from first message if title is still `"New conversation"`.
4. Enqueues `process_chat_message` arq task.
5. Returns immediately — agent response arrives via WebSocket stream.
6. If the agent cannot infer a complete `RunConfig`, it streams a clarification question as `token` frames and a `done` frame with `run_id: null`; `run_id` is also `null` in the HTTP response.
7. On reconnect after WS disconnect, the client must re-fetch `GET /conversations/{id}/messages` to catch up on any frames missed during disconnection.

---

### WebSocket: Conversation Stream

#### `WS /ws/conversations/{conversation_id}/stream`
Streams agent response tokens and pipeline events for a conversation.

**Authentication**: send API key as query param `?api_key=<key>` (WebSocket does not support custom headers in browsers).

**Frame types**

`token` — streaming LLM response token:
```json
{ "type": "token", "payload": { "message_id": "uuid", "token": "Setting up" } }
```

`tool_call` — tool invocation event:
```json
{
  "type": "tool_call",
  "payload": {
    "message_id": "uuid",
    "tool_name": "run_deseq2",
    "status": "running",
    "summary": null
  }
}
```

`stage_update` — pipeline stage status change:
```json
{
  "type": "stage_update",
  "payload": {
    "run_id": "uuid",
    "stage_name": "differential_expression",
    "status": "completed"
  }
}
```

`done` — agent turn complete:
```json
{ "type": "done", "payload": { "message_id": "uuid", "run_id": "uuid" } }
```

`error` — agent or pipeline error:
```json
{ "type": "error", "payload": { "message": "Stage failed: alignment" } }
```

---

## Rate Limits
- `POST /runs`: 10 requests/minute per API key.
- `POST /conversations/{id}/messages`: 10 requests/minute per API key (same cost as POST /runs — triggers LLM call and potentially a full pipeline run).
- All other endpoints: 120 requests/minute per API key.

## CORS Policy
- In development: FastAPI must add `CORSMiddleware` allowing `http://localhost:3000` (Next.js dev server).
- In production: The frontend is served from the same origin (`/app`), so no CORS headers are needed for API requests. CORS middleware should allow only the known frontend origin — never `*` in production.

## Versioning
- API version in URL path: `/api/v1/`.
- Breaking changes increment major version; new endpoints may be added without version bump.
