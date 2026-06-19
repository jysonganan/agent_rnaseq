"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from slowapi.errors import RateLimitExceeded

from src.api.errors import http_exception_handler, rate_limit_handler, validation_exception_handler
from src.api.rate_limit import limiter
from src.api.routers.api_keys import router as api_keys_router
from src.api.routers.artifacts import router as artifacts_router
from src.api.routers.genomes import router as genomes_router
from src.api.routers.health import router as health_router
from src.api.routers.projects import router as projects_router
from src.api.routers.results import router as results_router
from src.api.routers.runs import router as runs_router
from src.api.routers.samples import router as samples_router
from src.api.ws.logs import ws_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="RNA-seq Agent API",
        version="0.1.0",
        description="Production-style computational pipeline agent for end-to-end RNA-seq analysis.",
    )

    app.state.limiter = limiter

    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)  # type: ignore[arg-type]

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

    return app


app = create_app()
