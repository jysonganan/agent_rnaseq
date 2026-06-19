# TASK_FE_11 — FastAPI: Serve Next.js Static Build

## Goal
Configure FastAPI to serve the compiled Next.js static export under `/app`, and update the Docker build to produce a single image containing both the FastAPI server and the pre-built frontend.

## Requirements
- `next.config.ts`: `output: 'export'` produces `frontend/out/` directory
- FastAPI mounts `frontend/out/` as `StaticFiles` at `/app`
- `GET /app/` returns the Next.js `index.html`; all SPA routes served via `index.html` fallback (Next.js static export generates per-route `index.html` files, so each route directory must be served)
- `Makefile`: `frontend-build` target runs `npm ci && npm run build` in `frontend/`
- Docker multi-stage build:
  - Stage 1 (`node-build`): installs Node deps, runs `npm run build`
  - Stage 2 (`python-runtime`): copies `frontend/out/` from stage 1 into `/app/frontend/out/`
  - FastAPI reads mount path from env var `FRONTEND_OUT_DIR` (default `/app/frontend/out/`)
- `docker-compose.yml`: in dev, keep Next.js dev server as separate service on port 3000 (proxies to API at port 8000); the static mount is for prod only
- `NEXT_PUBLIC_API_URL` in the static build must point to `/` (same host), not `localhost:8000`, so the browser uses relative paths when served from FastAPI

## Files to Create/Edit
| File | Action | Purpose |
|---|---|---|
| `frontend/next.config.ts` | Edit | Add `output: 'export'`, ensure `basePath: '/app'` is set |
| `src/api/main.py` | Edit | Mount `StaticFiles` at `/app` from `FRONTEND_OUT_DIR` |
| `docker/Dockerfile.api` | Edit | Multi-stage: node-build + python-runtime |
| `docker/docker-compose.yml` | Edit | Add `frontend-dev` service on port 3000 (dev only) |
| `Makefile` | Edit | Add `frontend-build` target |
| `frontend/.env.production` | Create | `NEXT_PUBLIC_API_URL=` (empty → relative URLs) |

## FastAPI Mount (in `main.py`)
```python
import os
from fastapi.staticfiles import StaticFiles

frontend_out = os.getenv("FRONTEND_OUT_DIR", "frontend/out")
if os.path.isdir(frontend_out):
    app.mount("/app", StaticFiles(directory=frontend_out, html=True), name="frontend")
```
The `html=True` parameter enables the 404→index.html fallback for client-side routing.

## Dockerfile Multi-Stage Sketch
```dockerfile
# Stage 1: build Next.js
FROM node:20-alpine AS node-build
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
ENV NEXT_PUBLIC_API_URL=""
RUN npm run build

# Stage 2: Python runtime (extends existing Dockerfile.api)
FROM python:3.11-slim AS python-runtime
...
COPY --from=node-build /build/out /app/frontend/out
ENV FRONTEND_OUT_DIR=/app/frontend/out
...
```

## Makefile Target
```makefile
frontend-build:
	cd frontend && npm ci && npm run build
	@echo "Frontend build complete: frontend/out/"
```

## Acceptance Criteria
- [ ] `make frontend-build` succeeds; `frontend/out/` contains `app/index.html` (or `app/chat/index.html` etc.)
- [ ] FastAPI dev startup mounts `frontend/out/` at `/app` when the directory exists
- [ ] `GET http://localhost:8000/app/` returns the Next.js app HTML (200)
- [ ] `GET http://localhost:8000/app/chat` returns an `index.html` (not 404)
- [ ] `GET http://localhost:8000/app/runs` returns an `index.html` (not 404)
- [ ] `GET http://localhost:8000/api/v1/health` still returns 200 (API not shadowed by static mount)
- [ ] Docker multi-stage build produces a single image: `docker build -f docker/Dockerfile.api .` succeeds
- [ ] In the Docker image, `FRONTEND_OUT_DIR` is set to `/app/frontend/out`
- [ ] `frontend-dev` Docker Compose service runs `npm run dev` on port 3000 with `NEXT_PUBLIC_API_URL=http://localhost:8000`

## Definition of Done
All acceptance criteria pass. Verified end-to-end: `docker compose up`, navigate to `http://localhost:8000/app/`, the chat UI loads and can authenticate.

## Dependencies
TASK_FE_01 (scaffold must exist with `npm run build` working), TASK_11_fastapi_service (FastAPI app structure), TASK_16_docker_and_deployment (existing Dockerfile.api to extend).

## Notes
- If `frontend/out/` does not exist at FastAPI startup (e.g. during backend-only development), the static mount is silently skipped. This is intentional to avoid breaking `pytest` runs without a frontend build.
- `basePath: '/app'` in next.config.ts means all Next.js asset paths are prefixed with `/app/`, matching the FastAPI mount point.
