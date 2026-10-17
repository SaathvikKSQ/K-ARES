"""Engine error taxonomy (FR-C4). Each class maps to an API error code.

The engine raises these; the API layer translates them into the standard
error envelope (specs/api/interface-contract.md Conventions).
"""

from __future__ import annotations


class EvaluationError(Exception):
    """Base class for evaluation engine errors."""

    code = "internal_error"

    def __init__(self, message: str, *, details: list[dict] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or []


class UnknownEvaluatorError(EvaluationError):
    """A selected metric id is not registered (HTTP 400)."""

    code = "validation_error"


class RunConfigError(EvaluationError):
    """Run creation inputs are invalid (HTTP 400)."""

    code = "validation_error"


class ApplicabilityError(EvaluationError):
    """One or more selected metrics are inapplicable (HTTP 422, FR-E2)."""

    code = "unprocessable"


class InvalidRunStateError(EvaluationError):
    """Operation not allowed for the run's current state (HTTP 409)."""

    code = "invalid_state"
