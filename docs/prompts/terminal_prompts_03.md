# Terminal Prompts — Executor End-to-End Validation (Nextflow & AWS Batch)

Continues `terminal_prompts_02.md`. Chronological record of the user prompts issued after
that log was written: committing the log, and planning, implementing and CI-validating real
Nextflow / AWS Batch execution. Each prompt is quoted verbatim and followed by what was
implemented, what was added, and what remained to do or unsolved at that point.

---

## 1. Commit the prompt log

**Prompt**
> yes

**Outcome**: Committed `docs/prompts/terminal_prompts_02.md` as `eedda6c` and pushed
`origin/main`. The user's local `.gitignore`, `frontend/tsconfig.tsbuildinfo` and
`__pycache__` changes were left uncommitted.

---

## 2. Push the frontend branch

**Prompt**
> push add_frontend too

**Outcome**: `origin/add_frontend` fast-forwarded to `eedda6c`.

---

## 3–4. Arithmetic

**Prompts**
> 1300/80

> 1300/88

**Outcome**: Answered 16.25 and ≈ 14.77. No repository changes.

---

## 5. Plan and implement real Nextflow and AWS Batch validation

**Prompt**
> based on your recap, the next step is a real Nextflow and AWS Batch run to confirm the executors. Please come up with a plan for the implementation and test and work on it.

**Decisions (asked of the user)**
- Local tools: **No local install**. No conda env or bioinformatics tools are installed on
  the developer machine by the agent.
- AWS: **Prepare scripts only**. The agent writes the infra (create/teardown) and smoke-test
  scripts plus docs; the user runs them with their own credentials. Nothing is created in AWS
  by the agent.

**Plan**: four validation levels. L0 is unit/integration tests with a fake `nextflow` and moto
S3. L1 is a real Nextflow `-stub-run` in CI. L2 is a local real run with real tools on a
synthetic dataset with a known answer. L3 is AWS Batch via `-profile awsbatch`.

**Implemented / added**
- **Synthetic truth dataset** (`scripts/e2e/make_test_data.py`): deterministic and about
  1.6 MB. It has one 37.5 kb chromosome and 24 two-exon genes with canonical GT–AG introns on
  both strands. There are 3 `control` + 3 `treated` samples with 75 bp paired-end,
  reverse-stranded (dUTP) reads. `truth.json` records 4 genes 4× up, 4 genes 4× down, and 3
  homozygous exonic SNPs.
- **Reference prep** (`scripts/e2e/prepare_reference.sh`): builds the faidx, the sequence
  dictionary and the STAR index, with `--docker IMAGE` and `--stub` modes.
- **E2E harness** (`tests/e2e/harness.py`, `test_executor_e2e.py`): registers a run and
  uploads inputs (local or S3), then drives `OrchestratorAgent.execute_run`.
  - Contract checks:
    - the run is completed;
    - each stage has a completed row per sample or per run;
    - the executor recorded per stage is correct;
    - tool versions are recorded, and come from the stub processes for L1;
    - every artifact exists.
  - Science checks (L2/L3):
    - STAR unique mapping ≥ 70 %;
    - HTSeq counted ≥ 70 %;
    - DESeq2 recovers ≥ 75 % of the true up and down genes, with ≤ 2 false positives;
    - GATK calls ≥ 2 of the 3 planted SNPs;
    - the report exists.
  - Writes a PASS/FAIL table and `e2e_report.json`.
  - Opt-in through `E2E_EXECUTOR`, `E2E_STUB`, `E2E_DATA_DIR`, `E2E_STAGES`, `E2E_S3_PREFIX`
    and `E2E_OUTPUT_ROOT`.
  - `tests/e2e/test_harness.py` always runs. It uses a stub-equivalent fake `nextflow` and
    checks that the synthetic reads really are reverse-stranded and carry the fold changes.
- **Real-run bugs found and fixed while preparing L2/L3**:
  - GATK rejects BAMs without read groups. STAR now gets `--outSAMattrRGline ID SM PL`
    locally and in Nextflow, with sanitized sample names.
  - Hard-coded process memory overrode the run settings and could exceed the host. Modules
    now use `params.threads` and `params.memory`, set from `execution.cpus` and `memory_gb`.
  - `NO_FILE` was a script-local variable that functions could not see. It is now a
    `noFile()` function in `main.nf`.
  - Nextflow tasks need `ps`, and AWS Batch staging needs the AWS CLI. `procps` and AWS CLI
    v2.15.30 (pinned) were added to `docker/Dockerfile.tools`.
  - Tool versions are now read from per-process `<sid>.<tool>.version.txt` files instead of
    being assumed from the pins.
- **Nextflow**:
  - `stub:` blocks in every module.
  - Profiles: `local` (docker), `localtools`, `awsbatch`, and `test` (2 CPUs, 2 GB).
  - New settings `NEXTFLOW_LOCAL_PROFILE` and `NEXTFLOW_EXTRA_ARGS`.
- **Pinned conda env** (`environment/rnaseq-tools.yml`): matches `docker/tool_versions.txt`,
  which `tests/tools/test_e2e_infra.py` enforces.
- **AWS Batch infra** (`infra/aws-batch/`):
  - `batch-stack.yaml` (CloudFormation) creates the S3 bucket with expiry, the ECR repo, a
    Spot compute environment that scales to 0, the job queue, and a worker IAM policy.
  - Scripts: `deploy.sh`, `build_push_tools_image.sh` (linux/amd64, git-SHA tag),
    `run_e2e.sh` (`--with-de`) and `teardown.sh`.
  - Credentials come only from the environment or IAM roles.
- **CI**: new job **Nextflow stub e2e**. It installs Java 17 and Nextflow 23.10.1, runs the
  harness with `E2E_STUB=1` and `NEXTFLOW_LOCAL_PROFILE=localtools,test`, and uploads the
  report and Nextflow logs.
- **Docs**:
  - New runbook `docs/testing/executor_e2e.md` (L0–L3, pass criteria, cost).
  - Updated `tool_contracts.md`, `architecture.md`, `README.md` and `.env.example`.

---

## 6. Commit and push

**Prompt**
> OK

**Outcome**:
- Two commits pushed to `origin/main`:
  - `f1f8ea1` applies ruff fixes to the four conversation API files, because CI lint was
    already failing on `main`.
  - `7f59d2a` is the executor e2e validation work (40 files, about +1,900 lines).
- The first CI run failed only in **Nextflow stub e2e**, at "Install Nextflow". The cause was
  `curl -o nextflow` colliding with the repository's `nextflow/` directory (curl exit 23).
- `287f2de` fixes this by downloading to `$RUNNER_TEMP` before moving the binary onto `PATH`.
- CI run 44776701079 on `287f2de` is **fully green**: Nextflow stub e2e, Lint, Unit Tests and
  Integration Tests all pass.
  - The stub e2e step really ran, for 132 s.
  - The `nextflow-stub-e2e` artifact (report and logs) was uploaded.
  - This is the first real Nextflow execution of the agent → Nextflow path, so **L1 is
    confirmed**.
- Local suite: 910 passed, 1 skipped. `ruff check` and `ruff format` are clean.

---

## 7. Diagnostics

**Prompt**
> claude doctor

**Outcome**: Not a repository task. The user was pointed to `/doctor`, or `! claude doctor`,
to run it in the session.

---

## 8. Prompt log (this document)

**Prompt**
> Also save my prompts (not include the claude model version and after the point you made terminal_prompts_02.md) and your final summary of what you implemented, added and things remain to do or unsolved each time -- save them as docs/prompts/terminal_prompts_03.md

**Outcome**: This file.

---

## Remaining / unsolved (as of this log)

- **L2 (local real tools)**: not yet run. It needs the conda env, or the tools image plus
  Docker, along with Java and Nextflow (and R + DESeq2 for DE on the worker). This is the
  user's step, per `docs/testing/executor_e2e.md`.
- **L3 (AWS Batch)**: not yet run.
  - It needs the user's AWS credentials, a VPC with subnets that have outbound internet
    access, and Java + Nextflow on the worker host.
  - The tools image should be built on an x86 host.
  - Run `teardown.sh` afterwards.
- GATK RNA-seq best-practice steps are not implemented: `MarkDuplicates` and
  `SplitNCigarReads`. Variant calls on spliced reads are therefore less accurate than best
  practice.
- `aws_batch`: splicing (rMATS) and genome-browser tracks still download BAMs to the worker.
  The worker does not checksum-verify S3 artifacts.
- Nextflow process logs stay on the worker; CloudWatch log streaming is not wired.
- Cancellation terminates Nextflow for the current sample only.
- There is no frontend button for `POST /runs/{id}/retry`.
- `alpha` and `lfc_threshold` given in chat are only range-checked; they are not confirmed
  with the user the way contrasts and read length are.
- `origin/add_frontend` is at `eedda6c` and does not include `f1f8ea1`–`287f2de`.
