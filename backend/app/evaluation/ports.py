"""Ports (hexagonal) the engine depends on (decisions D2/D3).

The engine is persistence-agnostic: the service layer implements these ports
against the database (``run_service.DbEnginePorts``); tests implement them
in-memory. Adapters come through the integration registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from app.evaluation.base import CaseData, CaseEvalInput, MetricValue
from app.models.enums import RunStatus

if TYPE_CHECKING:
    from app.integrations.base import TargetAdapter


@dataclass(frozen=True)
class RunPlan:
    """Everything the engine needs to execute one run (no ORM objects)."""

    run_id: str
    application_type: str
    capabilities: dict[str, bool]
    cases: list[CaseData]
    selected_metrics: list[dict[str, Any]]  # [{evaluator_id, version, config}]
    run_config: dict[str, Any]
    model_name: str | None = None


class EnginePorts(Protocol):
    """Persistence + adapter bridge implemented by the service layer."""

    def load_plan(self, run_id: str) -> RunPlan: ...

    def build_adapter(self, run_id: str) -> TargetAdapter: ...

    def is_cancel_requested(self, run_id: str) -> bool: ...

    def mark_running(self, run_id: str) -> None: ...

    def record_case(
        self, run_id: str, case_input: CaseEvalInput, metrics: list[MetricValue]
    ) -> None: ...

    def finish(
        self,
        run_id: str,
        *,
        status: RunStatus,
        summary_metrics: list[MetricValue],
        error_summary: dict[str, Any] | None,
        model_metadata: dict[str, Any],
        duration_ms: int,
    ) -> None: ...
