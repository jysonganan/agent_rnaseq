"""RFC 9457 Problem Details error handlers."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

_STATUS_META: dict[int, tuple[str, str]] = {
    400: ("Bad Request", "bad-request"),
    401: ("Unauthorized", "unauthorized"),
    403: ("Forbidden", "forbidden"),
    404: ("Not Found", "not-found"),
    409: ("Conflict", "conflict"),
    422: ("Unprocessable Entity", "validation-error"),
    429: ("Too Many Requests", "rate-limit-exceeded"),
}


def _problem(request: Request, status: int, title: str, detail: str, suffix: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "type": f"https://agent-rnaseq.io/errors/{suffix}",
            "title": title,
            "status": status,
            "detail": detail,
            "instance": str(request.url.path),
        },
        media_type="application/problem+json",
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    title, suffix = _STATUS_META.get(exc.status_code, ("Error", "error"))
    detail = str(exc.detail) if exc.detail else title
    return _problem(request, exc.status_code, title, detail, suffix)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    detail = "; ".join(
        f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in errors
    )
    return _problem(request, 422, "Unprocessable Entity", detail, "validation-error")


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    detail = getattr(exc, "detail", "Rate limit exceeded")
    return _problem(request, 429, "Too Many Requests", str(detail), "rate-limit-exceeded")
