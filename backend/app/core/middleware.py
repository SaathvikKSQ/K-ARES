"""HTTP middleware: request-id propagation (X-Request-ID).

Spec reference: specs/architecture/design.md §6 (observability).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import Token

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import new_request_id, request_id_ctx

_REQUEST_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns/propagates a request id and exposes it via contextvar + header."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        token: Token[str] = request_id_ctx.set(
            request.headers.get(_REQUEST_HEADER) or new_request_id()
        )
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers[_REQUEST_HEADER] = request_id_ctx.get()
        return response
