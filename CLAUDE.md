# agent_rnaseq — Claude Code Guidance

## Project Overview
Production-style computational pipeline agent for end-to-end RNA-seq analysis.
Supports bulk and single-cell RNA-seq, local execution, and AWS (S3 + Batch).
Outputs: differential gene expression, VCF calls, splicing analysis, GSEA, genome browser tracks, Streamlit dashboards, FastAPI service.

## Architecture Pattern
Routing-agent design built on **OpenAI Agents SDK** (agent runtime) + **LangGraph** (durable state, routing, memory).
One Orchestrator agent decomposes user intent and dispatches to specialist sub-agents; each sub-agent wraps deterministic tool calls.

## Tech Stack
| Layer | Technology |
|---|---|
| Agent runtime | OpenAI Agents SDK |
| State / routing | LangGraph |
| API server | FastAPI |
| ORM | SQLAlchemy + Pydantic |
| Local DB | SQLite (dev) / PostgreSQL (prod) |
| Bioinformatics tools | FastQC, STAR, Salmon, HTSeq, CellRanger, samtools, RSeQC, GATK, RSEM, DESeq2, Reactome |
| Genome browser | UCSC browser integration |
| Visualization | Streamlit |
| Pipeline orchestration | Nextflow |
| Containers | Docker + docker-compose |
| Cloud | AWS S3, AWS Batch |
| Testing | pytest |
| Language | Python (primary), R (DESeq2, Reactome) |

## Safety Rules
- **LLMs must NOT perform numerical calculations** — all quantitative steps (alignment, counting, DE, variant calling) run as deterministic Python/R tool calls.
- LLMs may: summarize validated results, choose tools, set parameters, route workflows.
- Every tool call result must be validated by schema before being passed to an LLM.
- See `docs/specs/safety_policy.md` for full policy.

## Directory Layout (planned)
```
agent_rnaseq/
├── CLAUDE.md
├── docs/
│   ├── architecture.md
│   ├── prompts/
│   └── specs/
│       ├── data_models.md
│       ├── api_contracts.md
│       ├── tool_contracts.md
│       └── safety_policy.md
├── tasks/           # Implementation task files
├── src/
│   ├── agents/      # Orchestrator + specialist agents
│   ├── tools/       # Deterministic tool wrappers
│   ├── workflows/   # Nextflow pipeline configs
│   ├── api/         # FastAPI routers
│   ├── db/          # SQLAlchemy models + migrations
│   ├── schemas/     # Pydantic schemas
│   ├── streamlit/   # Visualization app
│   └── r/           # R scripts (DESeq2, Reactome)
├── tests/
├── docker/
├── nextflow/
└── examples/
    └── scrnaseq/    # Single-cell example dataset + notebook
```

## Key Conventions
- All tool interfaces defined in `docs/specs/tool_contracts.md` before implementation.
- DB schema changes must update `docs/specs/data_models.md` first.
- API changes must update `docs/specs/api_contracts.md` first.
- No LLM-generated numbers may be written to the database.
- R scripts are called as subprocesses; results parsed and validated in Python.
- AWS credentials come from environment variables / IAM roles; never hardcoded.

## Running Tests
```bash
pytest tests/ -v
```

## Development Environment
```bash
# Start all services (API + DB + Streamlit + Redis + arq-worker)
docker compose -f docker/docker-compose.yml up -d

# Build Docker images
make docker-build

# Push images to ECR (set REGISTRY and IMAGE_TAG env vars first)
make docker-push

# Run integration tests in Docker
docker compose -f docker/docker-compose.yml \
               -f docker/docker-compose.test.yml \
               up --abort-on-container-exit --exit-code-from test-runner
```

See `docs/deployment.md` for full production deployment instructions (ECS, AWS Batch, Kubernetes).
