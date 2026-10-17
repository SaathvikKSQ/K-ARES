"""Evaluator registry + applicability resolver (FR-E2/FR-E3, decisions D4)."""

from __future__ import annotations

import re

from app.evaluation.base import EvaluatorFn, EvaluatorSpec
from app.evaluation.errors import UnknownEvaluatorError

_EVALUATOR_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

_SPECS: dict[str, EvaluatorSpec] = {}
_FUNCTIONS: dict[str, EvaluatorFn] = {}


def register(spec: EvaluatorSpec, fn: EvaluatorFn) -> None:
    """Single registration point for new evaluators (FR-E3)."""
    if not _EVALUATOR_ID_RE.match(spec.id):
        raise ValueError(f"Invalid evaluator id '{spec.id}' (expected 'domain.name')")
    if spec.scope not in ("case", "run"):
        raise ValueError(f"Evaluator '{spec.id}' has invalid scope '{spec.scope}'")
    if spec.id in _SPECS:
        raise ValueError(f"Evaluator '{spec.id}' is already registered")
    _SPECS[spec.id] = spec
    _FUNCTIONS[spec.id] = fn


def get(evaluator_id: str) -> tuple[EvaluatorSpec, EvaluatorFn]:
    """Look up a registered evaluator; raises UnknownEvaluatorError."""
    try:
        return _SPECS[evaluator_id], _FUNCTIONS[evaluator_id]
    except KeyError:
        raise UnknownEvaluatorError(f"Unknown evaluator '{evaluator_id}'") from None


def list_specs() -> list[EvaluatorSpec]:
    """All registered evaluator specs, sorted by id."""
    return sorted(_SPECS.values(), key=lambda s: s.id)


def ensure_loaded() -> None:
    """Import the evaluators package so the core metrics are registered."""
    import app.evaluation.evaluators  # noqa: F401


def resolve_applicability(
    spec: EvaluatorSpec,
    *,
    application_type: str,
    capabilities: dict[str, bool],
    available_fields: set[str],
    valid_case_count: int,
) -> str | None:
    """Return None when applicable, else a human-readable reason (FR-E2).

    ``available_fields``: dataset field names provided by at least one valid
    case. Absent-vs-empty semantics (dataset-format.md): an explicitly empty
    value (e.g., ``relevant_doc_ids: []``) counts as provided; absent = None.
    """
    if spec.application_types and application_type not in spec.application_types:
        return f"metric does not support application type '{application_type}'"
    if valid_case_count < 1:
        return "dataset version has no valid test cases"
    for cap in spec.capabilities_required:
        if not capabilities.get(cap, False):
            return f"application does not expose capability '{cap}'"
    for fld in spec.required_fields:
        if fld not in available_fields:
            return f"dataset does not provide field '{fld}'"
    return None


def split_applicable(
    metric_ids: list[str],
    *,
    application_type: str,
    capabilities: dict[str, bool],
    available_fields: set[str],
    valid_case_count: int,
) -> tuple[list[str], list[dict[str, str]]]:
    """Partition metric ids into applicable ids and inapplicable entries."""
    applicable: list[str] = []
    inapplicable: list[dict[str, str]] = []
    for mid in metric_ids:
        spec, _ = get(mid)
        reason = resolve_applicability(
            spec,
            application_type=application_type,
            capabilities=capabilities,
            available_fields=available_fields,
            valid_case_count=valid_case_count,
        )
        if reason is None:
            applicable.append(mid)
        else:
            inapplicable.append({"id": mid, "reason": reason})
    return applicable, inapplicable
