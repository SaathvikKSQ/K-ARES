"""Test-result and metric-result models (Modules C/E/F)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import CaseOutcome, MetricStatus, Provenance, ValueKind, str_enum
from app.models.types import JSONType

if TYPE_CHECKING:
    from app.models.evaluation import EvaluationRun


class TestResult(UUIDPrimaryKeyMixin, Base):
    """Result for one test case (one repeat) in a run."""

    __tablename__ = "test_results"

    evaluation_run_id: Mapped[object] = mapped_column(
        Uuid(), ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False
    )
    test_case_id: Mapped[object] = mapped_column(
        Uuid(), ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False
    )
    repeat_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    outcome: Mapped[CaseOutcome] = mapped_column(
        str_enum(CaseOutcome, "case_outcome"), nullable=False
    )
    actual_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_documents: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    citations: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    agent_trace: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    token_usage: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    ttft_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)  # sanitized
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[EvaluationRun] = relationship(back_populates="results")
    metric_results: Mapped[list[MetricResult]] = relationship(
        back_populates="test_result", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "ix_test_results_run_case_repeat",
            "evaluation_run_id",
            "test_case_id",
            "repeat_index",
            unique=True,
        ),
    )


class MetricResult(UUIDPrimaryKeyMixin, Base):
    """A single metric value (per case, or run-level aggregate row)."""

    __tablename__ = "metric_results"

    test_result_id: Mapped[object | None] = mapped_column(
        Uuid(), ForeignKey("test_results.id", ondelete="CASCADE"), nullable=True
    )
    evaluator_id: Mapped[str] = mapped_column(String(80), nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    value_kind: Mapped[ValueKind] = mapped_column(
        str_enum(ValueKind, "metric_value_kind"), nullable=False
    )
    status: Mapped[MetricStatus] = mapped_column(
        str_enum(MetricStatus, "metric_status"), nullable=False
    )
    unavailable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[Provenance] = mapped_column(
        str_enum(Provenance, "metric_provenance"), nullable=False
    )
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    test_result: Mapped[TestResult | None] = relationship(back_populates="metric_results")
