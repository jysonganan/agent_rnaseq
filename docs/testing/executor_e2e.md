# Executor end-to-end validation (Nextflow & AWS Batch)

How to prove that runs with `execution.executor = nextflow | aws_batch` really work — from the
API's `AnalysisRun` through `OrchestratorAgent.execute_run`, the LangGraph stage nodes, the
specialists' `compute`/`persist` split and the Nextflow backend, to the published files, DB rows
and scientific results.

## Test levels

| Level | What it proves | Needs | How |
|---|---|---|---|
| **L0** unit/integration | Python logic, fake `nextflow`, moto S3 | Python | `pytest tests/` (CI) |
| **L1** Nextflow stub run | Real Nextflow 23.10.1 parses `nextflow/main.nf`, every module runs its `stub:` block, the agent's CLI/params/profile wiring and published file names match the Python adapters | Java 17 + Nextflow | CI job **Nextflow stub e2e**, or locally (below) |
| **L2** local real run | Real tools on a synthetic dataset with a known answer: mapping, stranded counting, DESeq2 recovery of the true DE genes, GATK calls of planted SNPs, report | Java + Nextflow + tools (conda env **or** tools image + Docker) | `pytest tests/e2e` with `E2E_EXECUTOR=nextflow` |
| **L3** AWS Batch run | Same dataset on S3 + AWS Batch via `-profile awsbatch`, S3 artifacts, worker-side parsing of S3 outputs | AWS account + the L2 host prerequisites | `infra/aws-batch/*.sh` |

## The synthetic dataset (`scripts/e2e/make_test_data.py`)

Deterministic (seeded) and tiny (~1.6 MB): one 37.5 kb chromosome, 24 two-exon genes on both
strands (canonical GT–AG introns), 3 `control` + 3 `treated` samples, 75 bp paired-end
**reverse-stranded (dUTP)** reads — matching the pipeline's `htseq-count --stranded reverse`.
`truth.json` records 4 genes 4× up and 4 genes 4× down in `treated`, and 3 homozygous exonic SNPs
present in all reads. `tests/e2e/test_harness.py` checks (without any tools) that the reads really
are reverse-stranded and carry the fold changes.

`scripts/e2e/prepare_reference.sh <data_dir> [--docker IMAGE | --stub]` builds `genome.fa.fai`
(samtools), `genome.dict` (GATK) and a STAR index with GTF junctions and
`--genomeSAindexNbases` sized for the tiny genome; `--stub` writes placeholders for L1.

## Pass criteria (`tests/e2e/harness.py::verify`)

All levels: run `completed`; per stage one completed `PipelineStage` row per sample (heavy stages)
or one per run; `executor` = the requested executor for `qc`/`alignment`/`alignment_qc`/`quantification`/
`variant_calling` and `local` for worker-side stages; `tool_version` recorded; every `Artifact`
exists (local path or S3 object). L1 additionally requires the versions to come from the stub
processes (proves Nextflow, not a local fallback, produced them).

L2/L3 add the science checks:

| Check | Threshold |
|---|---|
| STAR uniquely mapped | ≥ 70 % for every sample |
| RSeQC `infer_experiment` strandedness (`alignment_qc`) | `reverse` for every sample (dUTP data) |
| HTSeq counted / total (reverse-stranded) | ≥ 70 % for every sample |
| DESeq2 true up / down genes (padj < 0.05, \|log2FC\| > 1, right sign) | ≥ 75 % each |
| DESeq2 false positives among the 16 non-DE genes | ≤ 2 |
| GATK PASS calls of the 3 planted SNPs (best sample) | ≥ 2 |
| `report.html` | exists |

Results are printed as a PASS/FAIL table and written to `<E2E_OUTPUT_ROOT>/e2e_report.json`.

## L1 — Nextflow stub run

Runs automatically in CI (`.github/workflows/ci.yml`, job **Nextflow stub e2e**; logs and the
report are uploaded as the `nextflow-stub-e2e` artifact). Locally:

```bash
# Java 17 + Nextflow 23.10.1 on PATH (e.g. the conda env below, or SDKMAN + curl -s get.nextflow.io)
E2E_EXECUTOR=nextflow E2E_STUB=1 NEXTFLOW_LOCAL_PROFILE=localtools,test \
  pytest tests/e2e/test_executor_e2e.py -v -s
```

## L2 — local real run

Option A — pinned conda env, no Docker (`environment/rnaseq-tools.yml`, ~4–5 GB; versions equal
`docker/tool_versions.txt`, enforced by `tests/tools/test_e2e_infra.py`):

```bash
# Apple Silicon: some pinned builds are Intel-only → osx-64 env under Rosetta
CONDA_SUBDIR=osx-64 conda env create -f environment/rnaseq-tools.yml   # Linux: drop CONDA_SUBDIR
conda activate rnaseq-tools
pip install -e ".[dev]"

python scripts/e2e/make_test_data.py --out ~/e2e_data
scripts/e2e/prepare_reference.sh ~/e2e_data

E2E_EXECUTOR=nextflow E2E_DATA_DIR=~/e2e_data NEXTFLOW_LOCAL_PROFILE=localtools,test \
  pytest tests/e2e/test_executor_e2e.py -v -s
# Same data, tools in-process instead of Nextflow:
E2E_EXECUTOR=local E2E_DATA_DIR=~/e2e_data pytest tests/e2e/test_executor_e2e.py -v -s
```

Option B — tools image + Docker (`NEXTFLOW_LOCAL_PROFILE=local,test`,
`NEXTFLOW_TOOLS_IMAGE=<image>`, `scripts/e2e/prepare_reference.sh <data> --docker <image>`); the
worker host still needs Java + Nextflow, and R + DESeq2 if `differential_expression` is included
(worker-side stage).

Default L2 stages: `qc, alignment, alignment_qc, quantification, variant_calling, differential_expression,
visualization, report` (override with `E2E_STAGES`; `visualization` needs deepTools on the worker).

## L3 — AWS Batch

```bash
# 0. AWS CLI v2 with credentials for the target account (an admin or a role allowed to create
#    S3, ECR, IAM roles/policies, Batch and EC2 security groups).
# 1. Create the stack (bucket, ECR repo, Spot compute env scaling to 0, queue, worker policy)
infra/aws-batch/deploy.sh --vpc-id vpc-xxxx --subnets subnet-aaaa,subnet-bbbb
# 2. Build + push the tools image (linux/amd64, immutable git-SHA tag) — large; prefer an x86 host
infra/aws-batch/build_push_tools_image.sh
# 3. Run: synthetic data → S3 → nextflow -profile awsbatch → verify
infra/aws-batch/run_e2e.sh            # heavy stages only
infra/aws-batch/run_e2e.sh --with-de  # + DESeq2 in the worker (needs R + DESeq2 locally)
# 4. Remove everything (asks for the stack name)
infra/aws-batch/teardown.sh
```

Subnets need outbound internet (public subnets with auto-assigned public IPs, or private subnets
with NAT) so instances can pull from ECR and reach S3. The worker identity needs the
`WorkerPolicyArn` stack output (batch submit/describe + bucket access).

**Cost.** Compute scales to zero; the test runs a few short Spot jobs on small instances — well
under US$1 per run in typical regions. S3 and ECR storage is billed until `teardown.sh`; S3 test
data also expires automatically after `DataRetentionDays` (default 7). The tools image is several
GB in ECR (~US$0.10/GB-month).

## What each level would catch (known real-run pitfalls, now fixed)

| Pitfall | Fixed by |
|---|---|
| GATK rejects BAMs without read groups | STAR `--outSAMattrRGline` (local + Nextflow) |
| Hard-coded process memory (e.g. 40 GB) exceeds the host / overrides run settings | modules use `--threads`/`--memory` from `execution.cpus`/`memory_gb` |
| Nextflow tasks need `ps` in the container | `procps` in `docker/Dockerfile.tools` |
| AWS Batch staging needs the AWS CLI in the container | AWS CLI v2 (pinned) in the tools image |
| `NO_FILE` defined as a script-local variable is invisible inside functions | `noFile()` function in `main.nf` |
| Reported `tool_version` assumed from pins | each process writes `<sid>.<tool>.version.txt`; adapters read it |
