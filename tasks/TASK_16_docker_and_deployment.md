# TASK-16: Docker Images, docker-compose, and Deployment Configuration

## Goal
Finalize all Docker images with pinned tool versions, complete docker-compose configuration for local dev, and document prod deployment topology.

## Requirements
- `Dockerfile.api`: Python 3.11, all bioinformatics tools installed with pinned versions.
- `Dockerfile.streamlit`: minimal Python image, streamlit only.
- `Dockerfile.tools`: heavy image with STAR, GATK, Salmon, HTSeq, samtools, CellRanger (or documented download step for licensed tools).
- `docker-compose.yml`: api, arq-worker, streamlit, db (PostgreSQL for compose parity), redis, tool containers.
- Redis service is required for ARQ task queue and WebSocket pub/sub log streaming.
- Version pins for all tools documented in `docker/tool_versions.txt`.
- No `latest` tags anywhere in production Dockerfiles.
- Health checks for all services including Redis.

## Files to Create
```
docker/
  Dockerfile.api
  Dockerfile.streamlit
  Dockerfile.tools      # Heavy bioinformatics image
  tool_versions.txt     # FastQC=0.12.1, STAR=2.7.11b, etc.
  docker-compose.yml    # Updated with all services
  docker-compose.test.yml  # Override for integration tests (SQLite, mocked AWS)
docs/
  deployment.md         # Prod deployment guide: ECS/K8s + AWS Batch topology
```

## Files to Edit
- `CLAUDE.md` — add Docker build instructions.
- `Makefile` — add `docker-build`, `docker-push` targets.

## Acceptance Criteria
- [ ] `docker-compose build` succeeds for all services.
- [ ] `docker-compose up -d` starts api, arq-worker, streamlit, db, redis; all health checks pass.
- [ ] `docker-compose -f docker-compose.test.yml up --abort-on-container-exit` runs integration tests and exits 0.
- [ ] No `latest` tag in any production Dockerfile (CI check).
- [ ] `tool_versions.txt` matches versions actually installed in `Dockerfile.tools`.
- [ ] API container responds to `GET /health` within 10 seconds of start.
- [ ] Streamlit container responds to `GET /` within 15 seconds of start.

## Definition of Done
All services start successfully. Integration tests pass in Docker test compose.
`docs/deployment.md` reviewed and complete.
