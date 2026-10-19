"""Core value objects for the evaluation engine (FR-E1, decisions D4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.models.enums import CaseOutcome, MetricStatus, Provenance, ValueKind


@dataclass(frozen=True)
class EvaluatorSpec:
    """Declaration of one metric evaluator (FR-E1).

    ``scope``: "case" evaluators run per test case; "run" evaluators compute
    run-level aggregates once all cases are recorded.
    """

    id: str
    name: str
    description: str
    version: str
    provenance: Provenance
    value_kind: ValueKind
    scope: str
    application_types: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()
    capabilities_required: tuple[str, ...] = ()
    config_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MetricValue:
    """Outcome of one evaluator invocation.

    Missing inputs produce ``status=unavailable`` with ``unavailable_reason``;
    the engine never fabricates values (constitution section 2.2).
    """

    evaluator_id: str
    evaluator_version: str
    provenance: Provenance
    value_kind: ValueKind
    status: MetricStatus
    score: float | None = None
    unavailable_reason: str | None = None
    explanation: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def unavailable(cls, spec: EvaluatorSpec, reason: str) -> MetricValue:
        return cls(
            evaluator_id=spec.id,
            evaluator_version=spec.version,
            provenance=spec.provenance,
            value_kind=spec.value_kind,
            status=MetricStatus.UNAVAILABLE,
            score=None,
            unavailable_reason=reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluator_id": self.evaluator_id,
            "evaluator_version": self.evaluator_version,
            "provenance": self.provenance.value,
            "value_kind": self.value_kind.value,
            "status": self.status.value,
            "score": self.score,
            "unavailable_reason": self.unavailable_reason,
            "explanation": self.explanation,
            "details": self.details,
        }

@dataclass(frozen=True)
class RepeatRecord:
    """One adapter invocation of one test case (repeat_index i)."""

    repeat_index: int
    outcome: CaseOutcome
    output: str | None = None
    latency_ms: int | None = None
    ttft_ms: int | None = None
    token_usage: dict[str, int] | None = None
    retrieved_document_ids: list[str] | None = None
    retrieved_documents: list[dict[str, Any]] | None = None  # {doc_id, content, ...}
    citations: list[str] | None = None  # cited doc ids in output order
    agent_trace: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class CaseData:
    """Test-case fields relevant for evaluation (from a dataset version)."""

    id: str
    position: int
    case_input: dict[str, Any]
    expected_output: str | None = None
    reference_context: str | None = None
    relevant_doc_ids: list[str] | None = None  # None = not labeled; [] = labeled empty
    expected_tool: dict[str, Any] | None = None
    expected_action_sequence: list[str] | None = None
    category: str | None = None
    external_id: str | None = None
    is_security_case: bool = False


@dataclass
class CaseEvalInput:
    """Input passed to case-scope evaluators."""

    case: CaseData
    repeats: list[RepeatRecord]
    config: dict[str, Any] = field(default_factory=dict)

    def successful_repeats(self) -> list[RepeatRecord]:
        """Repeats whose execution succeeded (independent of metric scores)."""
        return [r for r in self.repeats if r.outcome == CaseOutcome.SUCCESS]


@dataclass
class RunEvalInput:
    """Input passed to run-scope (aggregate) evaluators."""

    cases: list[CaseEvalInput]
    run_config: dict[str, Any]
    run_meta: dict[str, Any]
    config: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class EvaluatorFn(Protocol):
    """A registered evaluator callable (case- or run-scope per its spec)."""

    def __call__(self, inp: Any) -> MetricValue: ...
