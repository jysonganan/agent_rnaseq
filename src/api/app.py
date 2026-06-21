"""FastAPI application factory."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from src.api.errors import http_exception_handler, rate_limit_handler, validation_exception_handler
from src.api.rate_limit import limiter
from src.api.routers.api_keys import router as api_keys_router
from src.api.routers.artifacts import router as artifacts_router
from src.api.routers.conversations import router as conversations_router
from src.api.routers.genomes import router as genomes_router
from src.api.routers.health import router as health_router
from src.api.routers.projects import router as projects_router
from src.api.routers.results import router as results_router
from src.api.routers.runs import router as runs_router
from src.api.routers.samples import router as samples_router
from src.api.websocket.conversation_stream import ws_conv_router
from src.api.ws.logs import ws_router


def create_app() -> FastAPI:
    from src.config import get_settings

    settings = get_settings()

    app = FastAPI(
        title="RNA-seq Agent API",
        version="0.1.0",
        description="Production-style computational pipeline agent for end-to-end RNA-seq analysis.",
    )

    app.state.limiter = limiter

    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)  # type: ignore[arg-type]

    # CORS — origins controlled via CORS_ALLOW_ORIGINS env var (comma-separated)
    origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    _v1 = "/api/v1"
    app.include_router(health_router, prefix=_v1)
    app.include_router(genomes_router, prefix=_v1)
    app.include_router(projects_router, prefix=_v1)
    app.include_router(samples_router, prefix=_v1)
    app.include_router(runs_router, prefix=_v1)
    app.include_router(artifacts_router, prefix=_v1)
    app.include_router(results_router, prefix=_v1)
    app.include_router(api_keys_router, prefix=_v1)
    app.include_router(ws_router, prefix=_v1)
    app.include_router(conversations_router, prefix=_v1)
    app.include_router(ws_conv_router, prefix=_v1)

    # Mount Next.js static build at /app — silently skipped if out dir doesn't exist
    # (e.g. during backend-only development or pytest runs without a frontend build)
    frontend_out = os.getenv("FRONTEND_OUT_DIR", "frontend/out")
    if os.path.isdir(frontend_out):
        app.mount("/app", StaticFiles(directory=frontend_out, html=True), name="frontend")

    return app


app = create_app()
