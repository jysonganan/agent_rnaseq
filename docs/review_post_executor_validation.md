# Repository Review — after executor validation

**Date:** 2026-11-22 · **Baseline commit:** `0e0d374` (`main`; `add_frontend` is the same)

**Scope:** the repository checked against `CLAUDE.md`, `docs/architecture.md`, `docs/specs/*.md`,
`tasks/*.md`, `tasks_frontend/*.md` and the earlier `docs/review.md`. Covers backend, agents,
Nextflow, infrastructure, frontend and docs. A follow-up question about local versus cloud
agent-driven execution is answered in §5.

## 1. Where things stand

The overall design matches the plan:
- The orchestrator does the LLM reasoning (intent, follow-up questions, run plan, results
  narrative).
- The LangGraph stage nodes send each stage to a specialist sub-agent, which runs
  deterministic tools.
- Run state is checkpointed so a run can resume or be retried.
- Inputs are chosen by the user (DE contrasts, read length).
- The safety rules hold: no LLM-generated numbers, outputs are schema-validated, error
  messages are sanitized, and input files are re-checked against their MD5.

**Tests and CI**
- Local suite: **910 passed, 1 skipped**.
- CI on `main` is green: Lint, Unit, Integration, and **Nextflow stub e2e**.

**Executor validation levels**

| Level | What it is | Status |
|---|---|---|
| L0 | Unit tests with a fake `nextflow` and simulated S3 (moto) | ✅ |
| L1 | Real Nextflow 23.10.1 with stub tools, in CI | ✅ |
| L2 | Real tools on a synthetic dataset with known answers | ⏳ needs a local tools environment (not yet run) |
| L3 | AWS Batch | ⏳ needs AWS credentials (scripts in `infra/aws-batch/`, not yet run) |

## 2. Fix these first

| # | Finding | Where | Why it matters |
|---|---|---|---|
| 1 | ✅ **Fixed (2026-11-23).** **The run-log WebSocket checks no API key.** The conversation stream checks one; the run-log stream ignores the key the frontend sends. Now the key and run ownership are checked before the socket is accepted (close `4403` / `4404`). | `src/api/ws/logs.py` | Anyone who can reach the API can stream any run's logs. |
| 2 | ✅ **Fixed (2026-11-25).** **API keys are sent in the WebSocket URL** (`?api_key=…`). Now both sockets use a first-message handshake: the client connects with a clean URL and sends `{"type":"auth","api_key":…}` within 10 s; a URL carrying `api_key` is refused with `4403`. The frontend stops retrying on `4403`/`4404`. | `src/api/ws_auth.py`, `frontend/src/lib/websocket.ts` | Breaks the `CLAUDE.md` frontend rule ("never in URL params"), and keys end up in proxy and access logs. |
| 3 | ✅ **Fixed (2026-11-24).** **Every API key can see every run and project.** `created_by` is recorded but lists and reads aren't filtered by it. Now data is owned per principal (`APIKey.principal`): projects, samples, runs, results, artifacts, conversations, both WebSockets and chat sample selection are scoped, and foreign ids return 404. `/api-keys` is admin-only (`APIKey.is_admin`), and `API_KEY_BOOTSTRAP` works as the first admin key (it was never wired before). | `src/api/ownership.py`, `src/api/routers/*` | Fine for one user, wrong for several. |
| 4 | **RSeQC never runs.** QC always runs before alignment, so the QC step never has a BAM file to check. | `src/agents/stage_inputs.py::_qc` | Post-alignment checks (strandedness, gene-body coverage) are missing from every run. |
| 5 | **Strandedness is fixed.** HTSeq always uses `--stranded reverse`; Salmon uses auto-detect (`-l A`). Users can't set it and nothing detects it. | `src/tools/quantification/htseq.py`, `nextflow/modules/htseq.nf` | Unstranded or forward-stranded libraries are quietly undercounted, roughly by half or worse. |
| 6 | **Database migrations are a single `create_all`.** There is one revision, so later schema changes (agent state, executor and audit columns) can't upgrade an existing database. | `alembic/versions/0001_initial_schema.py` | Any production database with real data can't be upgraded safely. |
| 7 | **Chat-started runs always use `executor=local`** (see §5). | `src/agents/orchestrator.py` (`dispatch_from_chat`) | Chat can't use the Nextflow or AWS Batch executors. |

## 3. Not implemented yet

### Bioinformatics
- **Variant calling** skips the GATK steps recommended for RNA-seq: `MarkDuplicates`,
  `SplitNCigarReads` and base recalibration. Calls on spliced reads are lower quality.
- **Single-cell:**
  - It isn't in the Nextflow pipeline.
  - CellRanger is licensed, so it's commented out of the tools image.
  - The Streamlit single-cell page always shows "no data", because the viz stage never writes
    the `sc_umap` entry it looks for.
- **Splicing (rMATS)** has a Nextflow module but no workflow. It always runs on the worker; on
  AWS Batch the BAM files are downloaded to the worker first.
- **Other tools have never run for real.** CellRanger, rMATS, Scanpy and the R steps (DESeq2,
  Reactome GSEA) have only been tested with mocks. The L2 dataset covers DESeq2 but has not
  been run yet.

### Execution
- **Samples run one at a time** for every heavy stage, including on Batch. A 20-sample run
  takes about 20× as long as it needs to.
- **Cancelling** stops only the sample currently running.
- **Nextflow and Batch logs** stay on the worker. They aren't streamed to the run-log
  WebSocket or to CloudWatch.
- **Files on S3** aren't re-checked against their checksums by the worker.

### Product and API
- **No file upload or presigned upload URLs.** Users have to put FASTQs on the server's disk
  or in S3 themselves.
- **Frontend:**
  - Has chat, runs, artifacts and the genome browser.
  - Has no retry button and no screens for projects, samples or genomes.
  - Has no result tables (QC, DE, GSEA, variants, splicing), although the API already serves
    them.
  - Its lint, tests and build aren't in CI.
- **Streamlit** takes a typed local folder path instead of a run ID, and can't read results
  stored on S3.
- **Chat settings:**
  - `alpha` and `lfc_threshold` from chat are only range-checked, not confirmed with the user.
  - Strandedness isn't asked at all (see #5).
- **Earlier review items still open** (`docs/review.md`):
  - O2: observability (metrics and tracing).
  - O4: an archiving strategy for the large DE-results table.

### Docs and accuracy
- **"OpenAI Agents SDK"** is named in `CLAUDE.md`, `architecture.md` and `README.md`, but the
  code uses only the plain `openai` client, and the Agents SDK package isn't a dependency.
  Either adopt it or correct the docs.
- **Deployment guide:** the ECS and Kubernetes sections in `docs/deployment.md` have no
  matching infrastructure code. Only the AWS Batch stack exists.
- **Dead code:** `src/workflows/` is an empty package.

## 4. What to do next (suggested order)

1. **Security fixes** (small, about half a day):
   - Check the key on the run-log WebSocket.
   - Move WebSocket authentication out of the URL (a first message or a short-lived token).
   - Filter runs and projects by owner.
2. **Correct science:**
   - Add a `strandedness` setting, asked in chat like read length, or auto-detected.
   - Move RSeQC to a post-alignment QC step.
   - Add `MarkDuplicates` and `SplitNCigarReads` to variant calling, locally and in Nextflow.
3. **Executor choice in chat:** set by the user or server settings, never by the LLM. Details
   in §5 (about half a day).
4. **Run L2 and L3** using `docs/testing/executor_e2e.md`. The synthetic dataset's known
   answers check items 2–3.
5. **Proper Alembic migrations:** a real baseline revision plus one for the later changes, and
   a CI check that the models match the migrations.
6. **Parallel samples:** submit one Nextflow run per sample concurrently, or one multi-sample
   Nextflow run per stage, with a concurrency limit.
7. **Frontend completeness:**
   - A retry button and result-table pages.
   - Upload with presigned S3 URLs.
   - Frontend lint, tests and build in CI.
8. **Single-cell and splicing in Nextflow**, plus UMAP output for Streamlit.
9. **Observability:** structured logs, Nextflow and Batch logs streamed into the run-log
   WebSocket, and basic metrics.

Items 1 and 2 come first: they're small and they close a security hole and a silent counting
error.

## 5. Follow-up: is agent-driven execution local only?

**No.** Cloud execution already works for runs created through the API. Only runs started
from **chat** are fixed to local, by one hard-coded value.

### Two ways to start a run, the same agent code

| Entry point | Executor | Where it's set |
|---|---|---|
| `POST /runs` (API) | `local`, `nextflow` or `aws_batch`, whatever the request body says | `execution.executor` in `CreateRunIn` |
| Chat (`dispatch_from_chat`) | **always `local`** | `executor=Executor.local` in `src/agents/orchestrator.py` |

Both paths end in `OrchestratorAgent.execute_run`. It reads the executor from the run's
config, checks the prerequisites (`_configure_executor`), and sends the heavy per-sample
stages to Nextflow, either on the local machine (`nextflow`) or on AWS Batch (`aws_batch`).
A chat run never asks for anything except `local`.

### Why chat is local only
1. **It's left over from older code.** The line came in with the conversation API work
   (`f38e1f2`, TASK_FE_10), before the Nextflow and AWS Batch executors existed, when `local`
   was the only real option. When those executors were added, the API path was wired up and
   the chat path wasn't revisited. That was an oversight, not a design limit.
2. **The LLM shouldn't choose it, so a plain pass-through would be wrong.** The executor
   decides what infrastructure runs and what it costs, much like `dry_run`, which the code
   already says must never be set by the LLM.

### What it takes to enable it in chat
- **The executor comes from a person or from settings, never from the LLM.**
  - Add a server setting, e.g. `DEFAULT_EXECUTOR`.
  - The user can override it by naming it in chat ("run it on AWS Batch"). This gets the same
    guard as contrasts and read length, which accept a value only if the user actually stated
    it.
- **Check prerequisites before the run is created,** not when it fails:
  - `aws_batch` needs `S3_ARTIFACT_BUCKET`, `AWS_BATCH_JOB_QUEUE` and `s3://` sample paths;
  - `nextflow` needs `nextflow` installed on the worker.
  - If something is missing, the agent asks a clarifying question, the way it does for a
    missing read length.
- **Show the executor in the run plan,** and ask for confirmation before anything is sent to
  AWS, since that costs money.
- **Tests** in the style of `tests/agents/test_chat_contrasts.py`.

### Even with this fixed, a "cloud" run is only partly in the cloud
- Only the heavy per-sample stages (QC, alignment, quantification, variant calling) go to
  Batch.
- The orchestrator and the lighter stages (DE, GSEA, splicing, visualization, report) still
  run in the worker process, wherever it is deployed: a local machine, or ECS per
  `docs/deployment.md`.
- The AWS Batch path hasn't been run against real AWS yet (L3), so adding chat as an entry
  point doesn't prove Batch works.
