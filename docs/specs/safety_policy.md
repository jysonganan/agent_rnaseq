# Safety Policy

## Core Principle
**LLMs summarize validated results and choose tools/parameters. LLMs never perform or produce numerical calculations that enter the database or downstream analysis.**

---

## Rule 1 — No LLM Arithmetic

LLMs must not:
- Calculate fold changes, p-values, normalized counts, FPKM, TPM, NES scores, or any quantitative metric.
- Generate gene lists, pathway IDs, or variant calls from free text.
- Produce file paths by construction (e.g., guessing output directories).

LLMs may:
- Summarize pre-computed result tables in natural language.
- Decide which tools to call and with which validated parameters.
- Explain what a result means biologically.
- Route to the appropriate sub-agent.

**Enforcement**: Every numerical value written to the database must trace to a `ToolOutput` Pydantic model parsed from deterministic tool output. Agent code must never pass raw LLM text to a DB write operation.

---

## Rule 2 — Schema Validation at Every Boundary

Every tool call follows this sequence:
```
validate(ToolInput)        → raises ToolValidationError if invalid
run_tool(ToolInput)        → raises ToolExecutionError on non-zero exit
validate(raw_output)       → raises ToolValidationError if output malformed
store(ToolOutput)          → DB write, only after validation passes
pass_to_agent(ToolOutput)  → LLM receives typed summary, not raw stderr/stdout
```

No raw subprocess stdout may be passed to an LLM as a data source.

---

## Rule 3 — Deterministic R Scripts

DESeq2 and Reactome GSEA run as versioned R scripts (`src/r/`).
- Scripts are checked into version control and reviewed before use.
- Scripts are called as subprocesses with explicit argument passing.
- LLMs never generate or modify R script content at runtime.
- R script outputs (CSV files) are parsed and validated in Python before storage.

---

## Rule 4 — Reference Genome Selection

- Reference genomes are pre-registered in the `ReferenceGenome` table.
- Agents select genomes by ID, never by constructing paths from LLM text.
- FASTA/GTF/index paths come only from validated DB records.
- Agents are not permitted to register new genomes during a pipeline run.

---

## Rule 5 — Parameter Guardrails

LLM-chosen parameters must pass through `RunConfig` Pydantic validation before use.
Allowed parameter ranges enforced by validators:

| Parameter | Allowed Range / Values |
|---|---|
| `threads` | 1–256 |
| `memory_gb` | 1–512 |
| `alpha` (DE) | 0.001–0.1 |
| `lfc_threshold` | 0.0–5.0 |
| `min_count` | 1–1000 |
| `nperm` (GSEA) | 100–10000 |
| `max_pct_mt` (scRNA) | 5.0–50.0 |
| `aligner` | `star`, `salmon`, `rsem` (enum) |
| `executor` | `local`, `nextflow`, `aws_batch` (enum) |

Any parameter outside these bounds is rejected before tool invocation.

---

## Rule 6 — No Credential Exposure

- AWS credentials (access key, secret key) must come from environment variables or IAM roles.
- Credentials must never appear in: DB records, log files, agent messages, API responses, or report artifacts.
- Tool functions that call AWS APIs must use `boto3` session initialization — never string-interpolated keys.
- Credential scanning in CI is required before any merge to main.

---

## Rule 7 — Immutable Audit Log

Every tool invocation is recorded in `PipelineStage`:
- `input_params` (validated JSON, no credentials)
- `output_summary` (validated JSON summary of results)
- `started_at`, `completed_at`
- `executor`, `batch_job_id`

Audit records must not be deleted or modified after creation. `UPDATE` on `PipelineStage` is only permitted to set terminal status fields (`status`, `completed_at`, `error_message`).

---

## Rule 8 — Reproducibility

- Tool versions must be recorded at invocation time (`tool_version` field in `PipelineStage`).
- Docker images pin tool versions; floating tags (`latest`) are not permitted in production.
- `run_config` JSON snapshot is stored with every `AnalysisRun` and is immutable after run start.
- Random seeds for stochastic tools (e.g., UMAP) must be set and recorded.

---

## Rule 9 — Failure Handling

- Agent must not silently continue past a failed tool call.
- On `ToolExecutionError`, the stage is marked `failed` and the run halts (unless the stage is marked optional in the run config).
- Error messages stored in `PipelineStage.error_message` are sanitized: no file system paths or credentials.
- LLM receives only: stage name, tool name, exit code, and a truncated stderr (max 500 chars) for diagnosis assistance.

---

## Rule 10 — Output File Integrity

- MD5 checksums are computed and stored for all artifact files.
- Before any downstream tool consumes an artifact, its checksum is re-verified.
- S3 uploads use server-side encryption (SSE-S3 minimum).
- Output directories are run-scoped: `{output_root}/{run_id}/{stage_name}/`.

---

## Compliance Checklist (per implementation task)

- [ ] Tool input Pydantic model defined and reviewed.
- [ ] Tool output Pydantic model defined and reviewed.
- [ ] No LLM-generated numerics written to DB.
- [ ] R scripts are static files, not runtime-generated.
- [ ] Parameters validated against allowed ranges.
- [ ] Credentials sourced from environment, not hardcoded.
- [ ] Audit log writes present.
- [ ] Tool version recorded.
- [ ] Error handling does not silently continue.
- [ ] Output checksum computed.
