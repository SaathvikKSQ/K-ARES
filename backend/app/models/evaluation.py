"""Evaluation run and run-event models (Modules C/F)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import RunEventType, RunStatus, str_enum
from app.models.types import JSONType

if TYPE_CHECKING:
    from app.models.results import TestResult


class EvaluationRun(UUIDPrimaryKeyMixin, Base):
    """One execution of a dataset version against an application config."""

    __tablename__ = "evaluation_runs"

    application_id: Mapped[object] = mapped_column(
        Uuid(), ForeignKey("applications.id", ondelete="RESTRICT"), nullable=False
    )
    application_config_id: Mapped[object | None] = mapped_column(
        Uuid(), ForeignKey("application_configs.id", ondelete="RESTRICT"), nullable=True
    )
    dataset_id: Mapped[object] = mapped_column(
        Uuid(), ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False
    )
    dataset_version_id: Mapped[object] = mapped_column(
        Uuid(), ForeignKey("dataset_versions.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[RunStatus] = mapped_column(str_enum(RunStatus, "run_status"), nullable=False)
    selected_metrics: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    run_config: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    configuration_snapshot: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    summary_metrics: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    cost_summary: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    model_metadata: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    progress: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    error_summary: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    started_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    results: Mapped[list[TestResult]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    events: Mapped[list[RunEvent]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class RunEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only progress/audit events for a run."""

    __tablename__ = "run_events"

    evaluation_run_id: Mapped[object] = mapped_column(
        Uuid(), ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[RunEventType] = mapped_column(
        str_enum(RunEventType, "run_event_type"), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    run: Mapped[EvaluationRun] = relationship(back_populates="events")
