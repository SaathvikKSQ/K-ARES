"""Structured JSON logging with secret redaction.

Provides:
- ``JsonFormatter``: one-JSON-object-per-line logs with request ids.
- ``redact_secrets``: recursive redaction of sensitive mapping keys.
- ``request_id`` contextvar plumbing via ``RequestContextFilter``.

Spec references: specs/security/security-requirements.md SR-10, SR-29;
specs/architecture/design.md §6.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

# Keys whose values must never appear in logs (case-insensitive match).
SENSITIVE_KEY_PATTERN = re.compile(
    r"(api[_-]?key|token|password|secret|authorization|credential)", re.IGNORECASE
)
REDACTED = "***REDACTED***"


def redact_secrets(value: Any) -> Any:
    """Recursively redact values of sensitive keys in mappings.

    Non-dict/list values are returned unchanged; keys matching
    ``SENSITIVE_KEY_PATTERN`` have their values replaced by ``REDACTED``.
    """
    if isinstance(value, dict):
        return {
            k: (REDACTED if SENSITIVE_KEY_PATTERN.search(str(k)) else redact_secrets(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(v) for v in value]
    return value


class RequestContextFilter(logging.Filter):
    """Injects the current request id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class JsonFormatter(logging.Formatter):
    """Minimal structured JSON formatter (no external deps)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        # Redacted extras only; never log raw bodies (SR-29).
        extras = {
            k: redact_secrets(v)
            for k, v in record.__dict__.items()
            if k
            not in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "taskName",
                "request_id",
                "message",
            }
        }
        if extras:
            payload["extra"] = extras
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging with the JSON formatter and request-id filter."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestContextFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Uvicorn loggers propagate into the root handler for uniform output.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True


def new_request_id() -> str:
    """Generate a fresh request id."""
    return uuid.uuid4().hex


def get_request_id() -> str:
    """Return the request id for the current context."""
    return request_id_ctx.get()
