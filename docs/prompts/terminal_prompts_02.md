# Terminal Prompts — Non-Dry-Run Execution & Agent Dispatch

Chronological record of the user prompts issued while implementing real (non-dry-run)
pipeline execution, LangGraph → specialist sub-agent dispatch, user-decided DE contrasts,
the review/hardening pass, and the remaining "still missing" items. Each prompt is quoted
verbatim and followed by the summary of what was implemented, what was added, and what
remained to do or unsolved at that point.

---

## 1. Implement non-dry-run mode and graph dispatch to specialist agents

**Prompt**
> the non-dry run mode hasn't been implemented in this repo of agent for RNA-Seq analysis. The current graph still uses stub stage nodes and it doesn't yet dispatch to QCAgent or other specialists agents. we use the orchestrator agent to do LLM reasoning and the subagents for determinitic code or tool running.

**Context**: `src/agents/router.py` built every stage node with `_make_stub_node` (marks the
stage complete, runs nothing). The specialists existed but expected stage-specific inputs
that nothing constructed, and the ARQ `run_pipeline` job was a `pass`.

**Implemented / added**
- `src/agents/stage_inputs.py` (new) — builds each specialist's typed input deterministically
  from the DB (run, samples, genome) and upstream `stage_outputs`; per-sample stages
  (`qc`, `alignment`, `quantification`, `variant_calling`, `scrna_seq`) vs per-run stages.
- `src/agents/stage_executor.py` (new) — real LangGraph stage nodes: cancellation check,
  input building, specialist dispatch, commit, `stage_outputs`, checkpoint to
  `AnalysisRun.agent_state`, failure → `failed_stage`.
- `router.build_pipeline_graph(node_factory=None)` — stubs remain the default for tests;
  real execution passes the stage-node factory.
- `OrchestratorAgent.execute_run(db, run_id)` — re-validates the plan, canonical stage
  order, resumes from checkpoint (completed stages skipped, failed stage retried).
- `src/tools/de/count_matrix.py` (new, spec'd first in `tool_contracts.md`) —
  `build_count_matrix` (HTSeq/Salmon/RSEM) and `write_sample_metadata` for DESeq2.
- ARQ `run_pipeline` implemented (`execute_run_sync`, per-job DB session, thread offload);
  `src/worker.py` added (docker-compose referenced it but it didn't exist).
- Chat runs now get `RunSample` rows and are enqueued for execution.
- AlignmentAgent exposes sorted BAM/BAI (and a transcriptome BAM for RSEM); VizAgent skips
  UCSC tracks when no BAMs exist.
- 21 new tests (824 total passing).

**Remaining / unsolved**
- `generate_ucsc_tracks`, `prepare_streamlit_data`, `compile_report` were still
  `NotImplementedError` → `visualization` and `report` stages would fail for real.
- Pre-existing bug: `dispatch_from_chat` called `ToolValidationError` with one argument.
- LLM stage summaries (architecture §4) not implemented.
- Only `executor = local` accepted.
- DE contrasts were derived automatically in a narrow case (two conditions + a control-like
  label) — flagged as a decision worth checking.

---

## 2. Make DE contrasts (and other scientific decisions) user inputs

**Prompt**
> add the design or inputs so that the "Decision worth Checking" and implement it. Make DE contrasts flexible (not just work for two conditions) and ask the user to provide contrasts and use the user input for the decision.

**Implemented / added**
- Specs first: `api_contracts.md` "Analysis inputs" table (`de_contrasts`, `read_length`,
  sample `condition`), `tool_contracts.md` chat-gateway guards, `data_models.md`.
- `DEContrast` schema hardened: optional `name` defaulting to `<numerator>_vs_<denominator>`,
  filename-safe pattern, no self-comparison.
- `src/agents/run_requirements.py` (new) — one deterministic checker used by `POST /runs`
  (422), chat (follow-up question) and `execute_run` (refuse to start); any number of
  conditions/contrasts; replicate check; read length from the user or shared sample metadata.
- Chat (`dispatch_from_chat`): conversation history sent to the intent LLM; contrasts kept
  only if both conditions exist **and** were named by the user; read length kept only if the
  number appears in the user's messages; deterministic clarification question listing the
  conditions and the `<test> vs <reference>` format; deterministic "Run plan" echoed back;
  `ToolValidationError` calls fixed.
- Splicing runs once per contrast; automatic contrast derivation removed.
- 25 new tests (849 total).

**Remaining / unsolved**
- `alpha` / `lfc_threshold` from chat only bounded by Pydantic ranges (not checked against
  the user's text).
- No frontend run-creation form (contrasts come via chat or the REST API).

---

## 3. Commit and merge to main

**Prompt**
> commit the changes and merge the changes to the main branch

**Outcome**: Committed as `267688c` on `add_frontend` (only files from this work; local
`.gitignore`, `tsconfig.tsbuildinfo` and `__pycache__` changes left uncommitted). `main`
fast-forwarded to it with `git fetch . add_frontend:main` because an uncommitted file blocked
checkout. Brought the 15 earlier `add_frontend` commits (frontend tasks) onto `main` too.

---

## 4. Push main

**Prompt**
> yes, push main to origin

**Outcome**: `origin/main` `a6f8e19 → 267688c` (fast-forward).

---

## 5. Push add_frontend

**Prompt**
> push add_frontend too

**Outcome**: `origin/add_frontend` `defc00c → 267688c` (fast-forward).

---

## 6. Switch branch

**Prompt**
> switch to main branch

**Outcome**: Checked out `main` (same commit as `add_frontend`; local changes carried over).

---

## 7. Review the work against the specs and update the docs

**Prompt**
> Let's revisit what I have asked you to work on and review whether you complete it correctly. Also review CLAUDE.md, docs/architecture.md, docs/specs/.md, tasks/*.md, and the prompts docs/prompts/01_planner_prompt.md and docs/prompts/02_reviewer_prompt.md. "the non-dry run mode hasn't been implemented in this repo of agent for RNA-Seq analysis. The current graph still uses stub stage nodes and it doesn't yet dispatch to QCAgent or other specialists agents. we use the orchestrator agent to do LLM reasoning and the subagents for determinitic code or tool running." Besides what I have asked you to do for this, also update the docs/architecture.md and README.md and docs/specs if needed for the change you made and implementation for the non-dry run and graph dispatch to subagents and other following changes in previous commits.

**Review verdict**: the core request was met; three gaps were found in the dispatch path and
fixed.

**Implemented / added**
- Failure handling: the failing invocation's uncommitted result rows are rolled back; a
  `failed` `PipelineStage` audit row (with `input_params`) is kept; finished samples/contrasts
  are checkpointed as `partial` and skipped on resume (no duplicate rows).
- Audit fields (Rule 7): `input_params`, `started_at`, `completed_at`, `executor` via
  `BaseSpecialistAgent.run_stage()`.
- Artifact size + MD5 for local files (Rule 10).
- Sanitized run/stage error messages (Rule 9) via shared `src/agents/sanitize.py`.
- Progress events (`src/agents/run_events.py`): `logs:{run_id}` run-log frames;
  `stage_update` / `tool_call` / `error` frames on the conversation channel for chat runs
  (formats per spec; the frontend already consumed them, nothing published them before).
- `POST /runs` accepts `dry_run`.
- Docs: `architecture.md` (§3.1 execution path, §3.2 user-decided inputs, LLM boundary,
  events, chat flow), `api_contracts.md`, `tool_contracts.md` (§11b stage execution
  contract), `data_models.md`, `safety_policy.md` Rule 9, `README.md`.
- 860 tests passing.

**Remaining / unsolved (the "still missing" list)**
1. LLM stage summaries described in the architecture.
2. `visualization` and `report` tools not implemented.
3. Dry-run fixtures not loaded (dry runs completed with empty outputs).
4. Checksum re-verification before downstream use (Rule 10).
5. Only the `local` executor (no Nextflow / AWS Batch).
6. Rule 7 vs. specialists updating `tool_version` / `output_summary` at completion.
7. No API endpoint to retry/resume a failed run.

---

## 8. Commit and push the review fixes

**Prompt**
> yes

**Outcome**: Committed as `1f48bb3`, pushed `origin/main` `267688c → 1f48bb3`.

---

## 9. Work on the "still missing" items

**Prompt**
> work on the Still Missing you identified.

**Decision asked**: how `nextflow` / `aws_batch` runs should execute. **Answer**: Nextflow
offload — heavy per-sample stages run through the `nextflow/` workflows (`-profile local` or
`awsbatch`); light stages stay in the worker.

**Implemented / added**
1. **Visualization & report tools** (spec'd first): `prepare_streamlit_data` (dashboard
   `manifest.json`, combined DE/GSEA CSVs with a `contrast` column — verified with the
   dashboard's own loader), `generate_ucsc_tracks` (deepTools `bamCoverage` CPM bigWigs +
   UCSC track hub; deepTools 3.5.5 pinned in the tools image), `compile_report`
   (`report.md` + `report.html`, HTML-escaped, numbers from validated outputs). `GSEAAgent`
   now returns every contrast, not just the last.
2. **Dry-run fixtures**: 10 per-stage fixtures in `src/tools/mock_outputs/` (package data),
   validated against their ToolOutput models on load (`src/tools/mock_registry.py`), used by
   default for dry runs.
3. **Rule 10**: `src/agents/artifact_integrity.py` re-hashes local upstream artifacts before
   a stage runs; missing/changed file fails the stage.
4. **Run summary in chat**: `OrchestratorAgent.summarize_run` + `src/agents/run_summary.py` —
   deterministic Results list from validated outputs + one numbers-free LLM narrative
   (sentences with digits dropped); posted as an assistant message with `token` + `done`
   frames.
5. **Rule 7** clarified in `safety_policy.md` (updatable at completion: `status`,
   `completed_at`, `tool_version`, `output_summary`, `exit_code`); stage rows record the
   executor that actually ran the tools.
6. **`POST /runs/{id}/retry`** — re-queues failed/cancelled runs, resumes from checkpoint
   (409 for other statuses).
7. **Nextflow / AWS Batch executors**: QC/Alignment/Quantification/Variant specialists split
   into `compute` + `persist`; `src/tools/nextflow/stage_runner.py` runs one workflow per
   sample, polls for cancellation, and rebuilds the same validated ToolOutputs from published
   files; `src/tools/nextflow/storage.py` handles local vs S3 paths. Executor prerequisites
   checked at start (`nextflow` on PATH; for `aws_batch` bucket, Batch queue and `s3://`
   inputs). Nextflow pipeline fixed: `publishDir` everywhere, correct BAM channels for
   quantification/variant calling, single-end support (`NO_FILE`), GATK `.fai`/`.dict`
   staging, all processes in the pinned tools image. Worker image gains Java + Nextflow
   23.10.1 + the pipeline files. New settings `NEXTFLOW_BIN`, `NEXTFLOW_TOOLS_IMAGE`.
- Fix: gzip-aware VCF variant counting (affected local runs too).
- Docs: specs (`tool_contracts.md` "Executors" + "Nextflow backend", mock fixtures, viz/report
  formats; `api_contracts.md` retry, executors, summary message; `data_models.md`;
  `safety_policy.md` Rules 7/8/10), `architecture.md`, `README.md`, `.env.example`.
- 895 tests passing (Nextflow/S3 paths tested with a fake `nextflow` process and moto S3).

**Remaining / unsolved**
- Nextflow and AWS Batch paths not yet run against a real Nextflow install or AWS account.
- `aws_batch`: splicing (rMATS) and genome-browser tracks download BAMs to the worker; S3
  artifacts are not checksum-verified by the worker.
- `nextflow` executor needs Docker available to the worker.
- Cancellation terminates Nextflow for the current sample only.
- Nextflow process logs stay on the worker; CloudWatch log streaming not wired.
- No frontend button for retry.

---

## 10. Commit and push

**Prompt**
> yes

**Outcome**: Committed as `1b622fe` (65 files), pushed `origin/main` `1f48bb3 → 1b622fe`.
`origin/add_frontend` remains at `267688c`.

---

## 11. Prompt log (this document)

**Prompt**
> Also save my prompts (not include the claude model version) and your final summary of what you implemented, added and things remain to do or unsolved each time -- save them as docs/prompts/terminal_prompts_02.md

**Outcome**: This file.
