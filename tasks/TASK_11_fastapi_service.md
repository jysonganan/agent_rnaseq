# TASK-11: FastAPI Service

## Goal
Implement the FastAPI application with all endpoints defined in `docs/specs/api_contracts.md`, WebSocket log streaming, and API key authentication middleware.

## Requirements
- All REST endpoints from `api_contracts.md` implemented.
- WebSocket endpoint for run log streaming.
- API key auth middleware (Bearer token, keys stored in DB or env var list).
- Background task runner: `POST /runs` queues the pipeline in a `BackgroundTasks` worker.
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
    runner.py           # BackgroundTasks pipeline runner, connects to OrchestratorAgent
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
- [ ] `POST /runs` rate limit: 11th request in 1 minute returns 429.
- [ ] OpenAPI schema at `/docs` loads without error.

## Definition of Done
`pytest tests/api/` green. `uvicorn src.api.app:app` starts without errors.
