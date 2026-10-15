"""Standard error envelope and FastAPI exception handlers.

Every non-2xx response uses:
    {"error": {"code": ..., "message": ..., "details": [...]}, "request_id": ...}

Spec reference: specs/api/interface-contract.md (Conventions).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_request_id

logger = logging.getLogger(__name__)

_STATUS_TO_CODE = {
    400: "validation_error",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "unprocessable",
    500: "internal_error",
}


def error_response(
    status_code: int,
    message: str,
    code: str | None = None,
    details: list[dict] | None = None,
) -> JSONResponse:
    """Build a standards-compliant error response."""
    body = {
        "error": {
            "code": code or _STATUS_TO_CODE.get(status_code, "internal_error"),
            "message": message,
            "details": details or [],
        },
        "request_id": get_request_id(),
    }
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body))


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the standard error envelope to all error paths."""

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        details = [
            {
                "field": ".".join(str(loc) for loc in err.get("loc", [])),
                "message": err.get("msg", ""),
            }
            for err in exc.errors()
        ]
        return error_response(
            status.HTTP_400_BAD_REQUEST, "Request validation failed", details=details
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return error_response(exc.status_code, message)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Never leak internals to clients; log full detail server-side.
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error")
