# Deployment Guide: agent_rnaseq

## Topology Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Local Dev                                                      │
│  docker compose up -d                                           │
│  api (FastAPI) + arq-worker + streamlit + postgres + redis      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Production (ECS / Kubernetes)                                  │
│                                                                 │
│  ALB ──→ ECS Service: api (Fargate, 2+ replicas)               │
│           │                                                     │
│           ├──→ ECS Service: arq-worker (Fargate, 2+ replicas)  │
│           ├──→ ECS Service: streamlit (Fargate, 1 replica)     │
│           │                                                     │
│           ├──→ Amazon RDS: PostgreSQL 16                        │
│           ├──→ Amazon ElastiCache: Redis 7                      │
│           └──→ AWS Batch: compute environments for heavy jobs   │
│                           (alignment, variant calling, GSEA)   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Local Development

### Prerequisites
- Docker Desktop >= 4.28
- `docker compose` v2 (included with Docker Desktop)
- `.env.docker` file (see `.env.docker.example`)

### Start all services

```bash
docker compose -f docker/docker-compose.yml up -d
```

Services started:
| Service | URL | Notes |
|---|---|---|
| API | http://localhost:8000 | FastAPI + uvicorn |
| Streamlit | http://localhost:8501 | Visualization dashboard |
| PostgreSQL | localhost:5432 | DB: agent_rnaseq, user: agent_rnaseq |
| Redis | localhost:6379 | ARQ queue + WebSocket pub/sub |
| arq-worker | — | Background job processor |

### Stop

```bash
docker compose -f docker/docker-compose.yml down
# To also delete persisted volumes:
docker compose -f docker/docker-compose.yml down -v
```

### Build Docker images

```bash
make docker-build
```

### Run integration tests in Docker

```bash
docker compose -f docker/docker-compose.yml \
               -f docker/docker-compose.test.yml \
               up --abort-on-container-exit --exit-code-from test-runner
```

---

## Environment Variables

Create `.env.docker` in the project root (never commit secrets):

```dotenv
# Database
DATABASE_URL=postgresql://agent_rnaseq:agent_rnaseq_dev@db:5432/agent_rnaseq

# Redis
REDIS_URL=redis://redis:6379/0

# OpenAI
OPENAI_API_KEY=sk-...

# AWS (leave blank for local-only; required for S3/Batch workflows)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=us-east-1
AWS_S3_BUCKET=

# Output paths
OUTPUT_ROOT=/tmp/agent_rnaseq
```

In production, inject secrets via ECS task definition secrets (Secrets Manager) or Kubernetes Secrets. Never bake credentials into images.

---

## Building and Pushing Images

```bash
# Build all images
make docker-build

# Push to ECR (set REGISTRY and IMAGE_TAG first)
export REGISTRY=123456789.dkr.ecr.us-east-1.amazonaws.com
export IMAGE_TAG=v0.1.0
make docker-push
```

The `Makefile` targets build and push three images:
- `${REGISTRY}/agent-rnaseq-api:${IMAGE_TAG}`
- `${REGISTRY}/agent-rnaseq-streamlit:${IMAGE_TAG}`
- `${REGISTRY}/agent-rnaseq-tools:${IMAGE_TAG}` (heavy bioinformatics image)

---

## Production: AWS ECS + Fargate

### Infrastructure requirements

| Component | AWS Service | Notes |
|---|---|---|
| API | ECS Fargate (2 vCPU, 4 GB) | 2+ replicas behind ALB |
| ARQ worker | ECS Fargate (2 vCPU, 4 GB) | 2+ replicas |
| Streamlit | ECS Fargate (1 vCPU, 2 GB) | 1 replica (read-only) |
| Database | RDS PostgreSQL 16, db.t3.medium | Multi-AZ for prod |
| Cache/Queue | ElastiCache Redis 7, cache.t3.micro | Single node or cluster |
| Bioinformatics | AWS Batch (EC2, c5.4xlarge or larger) | On-demand or Spot |
| Artifacts | S3 bucket | Versioning enabled |

### ECS task definition (API service) — key settings

```json
{
  "cpu": "2048",
  "memory": "4096",
  "environment": [
    {"name": "DATABASE_URL", "value": "postgresql://...@rds-endpoint/agent_rnaseq"},
    {"name": "REDIS_URL",    "value": "redis://elasticache-endpoint:6379/0"},
    {"name": "OUTPUT_ROOT",  "value": "s3://your-bucket/outputs"}
  ],
  "secrets": [
    {"name": "OPENAI_API_KEY", "valueFrom": "arn:aws:secretsmanager:..."},
    {"name": "DATABASE_URL",   "valueFrom": "arn:aws:secretsmanager:..."}
  ],
  "healthCheck": {
    "command": ["CMD-SHELL", "curl -f http://localhost:8000/api/v1/health || exit 1"],
    "interval": 10,
    "timeout": 5,
    "retries": 3,
    "startPeriod": 15
  }
}
```

### AWS Batch setup

Heavy pipeline stages (alignment, variant calling) run on AWS Batch using the `Dockerfile.tools` image:

1. **Compute Environment**: EC2, c5.4xlarge or c5n.4xlarge, Spot or On-Demand.
2. **Job Queue**: one queue per environment tier (dev/prod).
3. **Job Definition**: references `agent-rnaseq-tools:${IMAGE_TAG}` from ECR.
4. **IAM role**: must have S3 read/write access to the artifact bucket.

Nextflow submits jobs to Batch automatically when configured with:

```
process {
    executor = 'awsbatch'
    queue    = 'agent-rnaseq-prod'
}
aws {
    region = 'us-east-1'
}
workDir = 's3://your-bucket/nextflow-work'
```

---

## Production: Kubernetes (alternative)

Deploy using Helm or raw manifests. Key considerations:

- Use `postgresql` and `redis` Helm charts for in-cluster dependencies, or point to managed services.
- Store secrets in Kubernetes Secrets (sealed with Sealed Secrets or external-secrets-operator).
- API and arq-worker Deployments share the same image (`agent-rnaseq-api`).
- Use a Horizontal Pod Autoscaler on the API deployment (CPU target: 60%).
- For Batch workloads, use the AWS Batch integration even from Kubernetes — do not run STAR/GATK jobs inside cluster pods.

---

## Health Checks

| Endpoint | Service | Expected response |
|---|---|---|
| `GET /api/v1/health` | API | `{"status": "ok"}` within 10 s |
| `GET /_stcore/health` | Streamlit | HTTP 200 within 15 s |
| `redis-cli ping` | Redis | `PONG` |
| `pg_isready -U agent_rnaseq` | PostgreSQL | exit 0 |

---

## Database Migrations

Run Alembic migrations before starting the API:

```bash
# Local
alembic upgrade head

# In Docker (before starting compose)
docker compose -f docker/docker-compose.yml run --rm api alembic upgrade head
```

For ECS, add a migration step as a Fargate task in the CI/CD pipeline that runs before the service update.

---

## Bioinformatics Tool Versions

All tool versions are pinned in `docker/tool_versions.txt` and installed in `docker/Dockerfile.tools`. To upgrade a tool:

1. Update the version in `docker/tool_versions.txt`.
2. Update the corresponding `ARG` in `docker/Dockerfile.tools`.
3. Run `make docker-build` and verify the new binary works.
4. Update `docs/specs/tool_contracts.md` if the tool interface changed.
