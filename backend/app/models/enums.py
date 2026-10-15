"""Enumerations used across the data model.

Values are stored as native strings (``native_enum=False``) so SQLite tests and
PostgreSQL share identical semantics; validation also exists at the Pydantic
layer (specs/architecture/data-model.md §Integrity Rules 4).
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class ApplicationType(StrEnum):
    RAG = "rag"
    LLM = "llm"
    AGENT = "agent"


class IntegrationType(StrEnum):
    MOCK = "mock"
    REST_API = "rest_api"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CaseOutcome(StrEnum):
    SUCCESS = "success"
    APPLICATION_ERROR = "application_error"
    TIMEOUT = "timeout"
    INVALID_CASE = "invalid_case"
    SKIPPED = "skipped"


class CaseStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


class MetricStatus(StrEnum):
    COMPUTED = "computed"
    UNAVAILABLE = "unavailable"


class Provenance(StrEnum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    MODEL_JUDGED = "model_judged"


class ValueKind(StrEnum):
    SCORE = "score"
    RATE = "rate"
    COUNT = "count"
    MS = "ms"
    TOKENS = "tokens"
    CURRENCY = "currency"
    BOOLEAN = "boolean"


class RunEventType(StrEnum):
    STARTED = "started"
    CASE_COMPLETED = "case_completed"
    PROGRESS = "progress"
    CANCELLED = "cancelled"
    FAILED = "failed"
    COMPLETED = "completed"
    WARNING = "warning"


class ArtifactKind(StrEnum):
    DATASET_FILE = "dataset_file"
    EXPORT = "export"
    ARTIFACT = "artifact"


def str_enum(enum_cls: type[StrEnum], name: str) -> object:
    """Build a SQLAlchemy column type for a StrEnum (stores values, not names)."""
    from sqlalchemy import Enum as SAEnum

    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        length=32,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )
