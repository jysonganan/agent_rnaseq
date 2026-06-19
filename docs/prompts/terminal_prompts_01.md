# Terminal Prompts — Post-Implementation (Tasks 1–16)

Chronological record of user prompts issued after the 16 implementation tasks
were completed. Prompts are grouped by intent and annotated with the outcome.

---

## 1. Commit and push TASK-15

**Prompt**
> commit the changes and push the commit to the remote github repo

**Context**: TASK-15 (Integration Tests & End-to-End Test Suite) had just been
implemented and all 781 tests were passing.

**Outcome**: Committed as `d86667a`. Pushed to `main`.

---

## 2. CI lint failure investigation

**Prompt**
> CI / Lint failed on github?

**Context**: GitHub Actions CI ran `ruff check` on the newly committed
integration test files and flagged multiple errors (unused imports, bare
`try/except/pass`, nested `with` statements, etc.).

**Outcome**: Root cause identified — ruff rules `I001`, `F401`, `SIM105`,
`SIM117`, `B008` all triggered. Fix prepared (see prompt 3).

---

## 3. Commit lint fix #1 (integration tests)

**Prompt**
> commit the changes and push the commit to the remote github repo

**Context**: Lint errors in the integration test files had just been fixed
(auto-fixed with `ruff --fix`, manual edits for `SIM117`/`SIM105`,
`# noqa: E402` added for conditional import).

**Outcome**: Committed as `e8552e3`. Pushed.

---

## 4. CI lint failure — second round

**Prompt**
> CI / Lint still failed on github

**Context**: The first lint fix resolved errors in `tests/integration/` but the
CI `lint` job also checks `src/`, which had pre-existing violations that were
never caught before CI existed. Key issues: `B008` (FastAPI `Depends()` in
argument defaults — correct idiom but ruff flags it), `SIM105` across
`src/api/ws/logs.py` and multiple specialist test files, and 47 files needing
`ruff format`.

**Outcome**: Added `"B008"` to global ruff ignore (FastAPI pattern is
intentional), applied `--unsafe-fixes` for `SIM105`, ran `ruff format` across
all of `src/` and `tests/`. Committed as `9f0c0bf`. Pushed. CI green.

---

## 5. Implement TASK-16

**Prompt**
> Read: CLAUDE.md, docs/architecture.md, docs/specs/*.md, tasks/TASK_16_*.md.
> Implement tasks/TASK_16_*.md only. Do not implement future tasks yet.
> After implementation: 1. show changed files 2. run pytest if available
> 3. summarize what was completed 4. stop

**Context**: Standard task-execution instruction used throughout the project.
TASK-16 covered Docker images, docker-compose, and deployment configuration.

**Outcome**: Created/edited 9 files:
- `docker/Dockerfile.api` — pinned base image, fixed CMD module path, added HEALTHCHECK
- `docker/Dockerfile.streamlit` — pinned base image, added HEALTHCHECK
- `docker/Dockerfile.tools` — new; installs all 16 bioinformatics tools from pinned versions
- `docker/tool_versions.txt` — new; canonical version manifest
- `docker/docker-compose.yml` — added PostgreSQL, arq-worker, health-condition `depends_on`
- `docker/docker-compose.test.yml` — new; SQLite + mocked AWS creds for CI
- `docs/deployment.md` — new; ECS/Fargate + AWS Batch + Kubernetes guide
- `CLAUDE.md` — updated dev environment section
- `Makefile` — added `docker-build` / `docker-push` targets

All 781 tests passed.

---

## 6. Commit and push TASK-16

**Prompt**
> commit the changes and push the commit to the remote github repo

**Outcome**: Committed as `557bb5d`. Pushed to `main`.

---

## 7. Write the repository README

**Prompt**
> You are a professional engineer. Add the README.md for this repo, covering
> the architecture, installation, usage, examples, local and s3 etc.

**Context**: No README existed. Request was for a production-quality document
covering all major aspects of the system.

**Outcome**: Created `README.md` (663 lines) covering:
- Architecture diagram (ASCII topology + component roles table)
- Pipeline stages with tools, outputs, and dependency rules
- Installation (Python, R/Bioconductor, bioinformatics tools)
- Configuration (env var reference with `.env.docker` template)
- Quick start — local (7-step curl walkthrough from API key to result download)
- Quick start — AWS S3 + Batch (S3 paths, `aws_batch` executor)
- Single-cell RNA-seq (scrnaseq pipeline type, PBMC 3k example)
- Full API endpoint table with rate limits
- Streamlit dashboard features
- Docker compose commands and `make` targets
- Project directory layout
- Safety policy condensed rules table
- Deployment pointer to `docs/deployment.md`

---

## 8. Commit and push README

**Prompt**
> commit the changes and push the commit to the remote github repo

**Outcome**: Committed as `f079297`. Pushed to `main`.

---

## 9. Demo data, notebook, and video recording scripts

**Prompt**
> include small example fastq files (e.g. from TCGA) in a ./data folder.
> And run this agent on the example data until generate the report and view
> results in the streamlit viewer. Make it as a jupyter notebook for running
> the agent on the sample data in the ./data folder. Also create a video demo
> showing the whole process for installing, running the agent and generating
> results (report and streamlit viewer).

**Context**: First end-to-end demo of the system. Real TCGA data requires
controlled dbGaP access, so synthetic FASTQ files were generated instead.
Bioinformatics tools are not installed locally, so `dry_run=True` mode was used
to route through all pipeline stages without invoking STAR/DESeq2/etc.

**Outcome**: Created 16 new/modified files committed as `2229483`:

| Path | Description |
|---|---|
| `data/ctrl_1_R1.fastq.gz` … `treat_2_R2.fastq.gz` | 8 synthetic paired-end FASTQ files (2 000 reads × 100 bp each) |
| `data/generate_data.py` | Reproducible data generator (GC-biased sequences per condition) |
| `data/README.md` | Dataset description and TCGA access note |
| `notebooks/demo.ipynb` | 11-cell Jupyter notebook (see below) |
| `demo/demo_commands.sh` | Shell script for asciinema terminal recording |
| `demo/RECORDING_GUIDE.md` | Four recording options: asciinema, GIF, MP4, OBS |
| `Makefile` | Added `demo` and `demo-record` targets |
| `README.md` | Added Demo section at top |
| `.gitignore` | Excluded `demo_output/`, cast/gif/mp4, `.ipynb_checkpoints/` |

**Notebook walkthrough** (`notebooks/demo.ipynb`):
1. Set environment variables before any `src` import
2. Verify / auto-generate FASTQ files in `data/`
3. Initialise SQLite database (10 tables via SQLAlchemy)
4. Register mock GRCh38 genome, project, 4 samples, API key
5. Dispatch `OrchestratorAgent` with `dry_run=True` through LangGraph (mocked LLM — no OpenAI key needed)
6. Generate realistic mock results: 300 DE genes (42 significant, padj ≤ 0.05), 25 Reactome GSEA pathways, 4-sample QC metrics
7. Write Streamlit data files (`de_results.csv`, `gsea_results.csv`, `qc_metrics.json`, `manifest.json`)
8. Render inline volcano plot, MA plot, and GSEA bubble chart using the same Plotly components as the Streamlit dashboard
9. Print `streamlit run` command with `STREAMLIT_DATA_DIR` pointing at generated files

Two bugs were caught and fixed during execution:
- `DetachedInstanceError` — ORM attributes accessed after SQLAlchemy session closed; fixed by capturing string values inside the `with Session` block
- `KeyError: 'baseMean'` — MA plot component expects camelCase `baseMean`; fixed column name in the data generation cell

**Video demo**: A real video file cannot be generated programmatically. Instead,
`demo/demo_commands.sh` is a complete automated terminal script designed to be
recorded with `asciinema rec --command bash demo/demo_commands.sh`. The recording
guide covers conversion to GIF (via `agg`) and MP4 (via `ffmpeg`), plus an OBS
screen-recording walkthrough script for browser + terminal demos.

---

## 10. Prompt summary (this document)

**Prompt**
> summarize my prompts after the task execution of task 1-16. Put the
> summarized prompts into doc/prompts/terminal_prompts_01.md

**Outcome**: This file.
