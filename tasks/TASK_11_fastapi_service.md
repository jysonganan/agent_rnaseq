# TASK-11: FastAPI Service

## Goal
Implement the FastAPI application with all endpoints defined in `docs/specs/api_contracts.md`, WebSocket log streaming, and API key authentication middleware.

## Requirements
- All REST endpoints from `api_contracts.md` implemented, including `/splicing`, `/variants`, and `/api-keys`.
- WebSocket endpoint for run log streaming (Redis pub/sub backend per `docs/architecture.md` Section 5).
- API key auth middleware: keys stored in `APIKey` DB table, looked up by SHA-256 hash of Bearer token.
- Pipeline runner: `POST /runs` enqueues the pipeline via ARQ (async Redis task queue). **Do NOT use FastAPI `BackgroundTasks`** — runs outlive the request lifecycle and must survive process restarts.
- `GET /projects/{project_id}` and `GET /samples/{sample_id}` single-resource endpoints.
- Pagination (`limit`/`offset`) on `GET /genomes` and `GET /projects`.
- Pydantic request/response schemas derived from `docs/specs/data_models.md`.
- RFC 9457 error responses.
- OpenAPI docs auto-generated (`/docs`).

## Files to Create
```
src/api/
  __init__.py
  app.py               # FastAPI app factory
  auth.py              # API key middleware / dependency
  routers/
    __init__.py
    health.py
    genomes.py
    projects.py
    samples.py
    runs.py
    artifacts.py
    results.py          # /qc, /de, /gsea endpoints
  ws/
    __init__.py
    logs.py             # WebSocket run log streaming
  background/
    __init__.py
    runner.py           # ARQ worker task: dequeues run_id, invokes OrchestratorAgent
  errors.py            # RFC 9457 exception handlers
tests/api/
  __init__.py
  conftest.py          # TestClient, in-memory DB override
  test_runs.py
  test_genomes.py
  test_results.py
  test_auth.py
```

## Files to Edit
- `src/config.py` — add `API_KEY_SECRET` or `API_KEYS` setting.
- `pyproject.toml` — add fastapi, uvicorn, httpx (test) dependencies.

## Acceptance Criteria
- [ ] `POST /runs` returns 202 with `run_id`.
- [ ] `GET /runs/{run_id}` returns 404 for unknown ID with RFC 9457 error body.
- [ ] `GET /runs/{run_id}` returns full stage list for a completed run.
- [ ] Request without `Authorization` header returns 401.
- [ ] `POST /runs` with invalid `alignment_mode` value returns 422.
- [ ] `GET /runs/{run_id}/de?contrast=X` returns 200 with paginated DE results.
- [ ] WebSocket `/ws/runs/{run_id}/logs` receives at least one message in integration test.
- [ ] `POST /runs` enqueues task via ARQ; run `status` is `pending` immediately; transitions to `running` when worker picks it up.
- [ ] API process restart does not lose pending runs (ARQ queue persists in Redis).
- [ ] `GET /runs/{run_id}/splicing` returns 200 with splicing results for completed run.
- [ ] `GET /runs/{run_id}/variants` returns 200 with variant results for completed run.
- [ ] `POST /api-keys` returns raw key once; subsequent `GET /api-keys` omits raw key.
- [ ] `DELETE /api-keys/{id}` sets `revoked_at`; subsequent requests with that key return 401.
- [ ] `POST /runs` rate limit: 11th request in 1 minute returns 429.
- [ ] OpenAPI schema at `/docs` loads without error.

## Definition of Done
`pytest tests/api/` green. `uvicorn src.api.app:app` starts without errors.
