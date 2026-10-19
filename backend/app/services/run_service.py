"""Evaluation run service: creation, queries, engine ports (FR-C/FR-F).

Runs are created async (202 + queued); a background worker claims and
executes them via the engine with DB-backed ports. Creation pins the dataset
version and a sanitized configuration snapshot so runs are reproducible
(decisions D10). Applicability is resolved before queueing; inapplicable
selections are rejected with 422 (FR-E2).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.evaluation import registry
from app.evaluation.base import CaseData, CaseEvalInput, MetricValue
from app.evaluation.engine import EvaluationEngine
from app.evaluation.errors import (
    ApplicabilityError,
    InvalidRunStateError,
    RunConfigError,
)
from app.evaluation.ports import RunPlan
from app.integrations.registry import get_adapter
from app.models.application import DEFAULT_CAPABILITIES, Application, ApplicationConfig
from app.models.dataset import Dataset, DatasetVersion, TestCase
from app.models.enums import CaseOutcome, CaseStatus, RunEventType, RunStatus
from app.models.evaluation import EvaluationRun, RunEvent
from app.models.results import MetricResult, TestResult
from app.schemas.run import RunCreate, ValidateConfigIn
from app.services.application_service import build_adapter_config

DEFAULT_RUN_CONFIG = {
    "concurrency": 4,
    "timeout_ms": 30000,
    "max_retries": 1,
    "repeats": 1,
    "rate_limit_rps": 0,
}


def _uuid(value: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise RunConfigError(f"{label} is not a valid UUID") from exc


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _now() -> datetime:
    return datetime.now(UTC)


def _get_application(session: Session, application_id: str) -> Application:
    app = session.get(Application, _uuid(application_id, "application_id"))
    if app is None:
        raise RunConfigError(f"application '{application_id}' not found")
    return app


def _get_dataset_version(
    session: Session, dataset_id: str, version_id: str | None
) -> tuple[Dataset, DatasetVersion]:
    dataset = session.get(Dataset, _uuid(dataset_id, "dataset_id"))
    if dataset is None:
        raise RunConfigError(f"dataset '{dataset_id}' not found")
    if version_id:
        version = session.get(DatasetVersion, _uuid(version_id, "dataset_version_id"))
        if version is None or version.dataset_id != dataset.id:
            raise RunConfigError(
                f"dataset version '{version_id}' not found for this dataset"
            )
    else:
        version = max(dataset.versions, key=lambda v: v.version_number, default=None)
        if version is None:
            raise RunConfigError("dataset has no versions")
    return dataset, version


def capabilities_of(app: Application) -> dict[str, bool]:
    """Merged capability flags (defaults + application-declared)."""
    caps = dict(DEFAULT_CAPABILITIES)
    for key, value in (app.capabilities or {}).items():
        if isinstance(value, bool):
            caps[key] = value
    return caps


def available_fields(session: Session, dataset_version_id: Any) -> set[str]:
    """Dataset fields provided by >= 1 valid case (absent-vs-empty aware)."""
    rows = session.execute(
        select(
            TestCase.expected_output,
            TestCase.relevant_doc_ids,
            TestCase.reference_context,
            TestCase.expected_tool,
            TestCase.expected_structured_output,
        ).where(
            TestCase.dataset_version_id == dataset_version_id,
            TestCase.status == CaseStatus.VALID,
        )
    ).all()
    fields = {"input"}
    for expected_output, relevant_doc_ids, reference_context, expected_tool, eso in rows:
        if expected_output is not None:
            fields.add("expected_output")
        if relevant_doc_ids is not None:
            fields.add("relevant_doc_ids")
        if reference_context is not None:
            fields.add("reference_context")
        if expected_tool is not None:
            fields.add("expected_tool")
        if eso is not None:
            fields.add("expected_structured_output")
    return fields


def _validate_metric_selection(metric_ids: list[str]) -> list[dict[str, Any]]:
    registry.ensure_loaded()
    selected: list[dict[str, Any]] = []
    for mid in metric_ids:
        spec, _ = registry.get(mid)
        selected.append({"evaluator_id": mid, "version": spec.version, "config": {}})
    return selected


def _check_applicability(
    session: Session, app: Application, version: DatasetVersion, metric_ids: list[str]
) -> tuple[list[str], list[dict[str, str]]]:
    return registry.split_applicable(
        metric_ids,
        application_type=app.application_type.value,
        capabilities=capabilities_of(app),
        available_fields=available_fields(session, version.id),
        valid_case_count=version.valid_case_count or 0,
    )


def _snapshot(
    session: Session, app: Application, dataset: Dataset, version: DatasetVersion,
    selected: list[dict[str, Any]], model_name: str | None,
) -> dict[str, Any]:
    return {
        "application": {
            "id": str(app.id),
            "name": app.name,
            "application_type": app.application_type.value,
            "integration_type": app.integration_type.value,
            "capabilities": capabilities_of(app),
            "invoke_path": app.invoke_path,
            "version_label": app.current_version_label,
            "model_name": model_name,
        },
        "dataset": {
            "id": str(dataset.id),
            "name": dataset.name,
            "version_id": str(version.id),
            "version_number": version.version_number,
            "content_hash": version.content_hash,
            "valid_case_count": version.valid_case_count,
        },
        "metrics": selected,
    }


def _latest_config(app: Application) -> ApplicationConfig | None:
    if not app.configs:
        return None
    return max(app.configs, key=lambda c: c.created_at)


def _validate_and_resolve(
    session: Session, payload: RunCreate | ValidateConfigIn
) -> tuple[Application, Dataset, DatasetVersion, list[dict[str, Any]]]:
    """Shared resolution for create and dry-run validate (400/404 paths)."""
    registry.ensure_loaded()
    app = _get_application(session, payload.application_id)
    dataset, version = _get_dataset_version(
        session, payload.dataset_id, payload.dataset_version_id
    )
    selected = _validate_metric_selection(payload.metric_ids)
    return app, dataset, version, selected


def create_run(session: Session, payload: RunCreate, triggered_by: str) -> EvaluationRun:
    """Validate inputs, resolve applicability, and enqueue a run (FR-C1)."""
    app, dataset, version, selected = _validate_and_resolve(session, payload)
    if not app.is_enabled:
        raise RunConfigError("application is disabled; enable it before running evaluations")
    applicable, inapplicable = _check_applicability(
        session, app, version, [m["evaluator_id"] for m in selected]
    )
    if inapplicable:
        raise ApplicabilityError(
            "selected metrics are inapplicable to this application/dataset pair",
            details=[
                {"field": "metric_ids", "message": f"{e['id']}: {e['reason']}"}
                for e in inapplicable
            ],
        )
    run_config = payload.run_config.model_dump()
    config_row = _latest_config(app)
    model_name = config_row.model_name if config_row else None
    run = EvaluationRun(
        application_id=app.id,
        application_config_id=config_row.id if config_row else None,
        dataset_id=dataset.id,
        dataset_version_id=version.id,
        status=RunStatus.QUEUED,
        selected_metrics=selected,
        run_config=run_config,
        configuration_snapshot=_snapshot(
            session, app, dataset, version, selected, model_name
        ),
        triggered_by=triggered_by,
        progress={
            "total": (version.valid_case_count or 0) * run_config["repeats"],
            "completed": 0,
            "failed": 0,
            "skipped": 0,
        },
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def validate_config(session: Session, payload: ValidateConfigIn) -> dict[str, Any]:
    """Applicability preview (dry-run; FR-C2)."""
    app, dataset, version, selected = _validate_and_resolve(session, payload)
    applicable, inapplicable = _check_applicability(
        session, app, version, [m["evaluator_id"] for m in selected]
    )
    return {
        "applicable": applicable,
        "inapplicable": inapplicable,
        "estimated_cases": version.valid_case_count or 0,
    }


def get_run_or_404(session: Session, run_id: str) -> EvaluationRun:
    run = session.get(EvaluationRun, _uuid(run_id, "run_id"))
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def to_summary(run: EvaluationRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "application_id": str(run.application_id),
        "dataset_id": str(run.dataset_id),
        "dataset_version_id": str(run.dataset_version_id),
        "status": run.status.value if isinstance(run.status, RunStatus) else str(run.status),
        "progress": run.progress or {},
        "metric_ids": [m["evaluator_id"] for m in (run.selected_metrics or [])],
        "triggered_by": run.triggered_by,
        "created_at": _iso(run.created_at),
        "started_at": _iso(run.started_at),
        "completed_at": _iso(run.completed_at),
        "duration_ms": run.duration_ms,
    }


def to_detail(run: EvaluationRun) -> dict[str, Any]:
    detail = to_summary(run)
    detail.update(
        {
            "run_config": run.run_config or {},
            "configuration_snapshot": run.configuration_snapshot or {},
            "summary_metrics": run.summary_metrics or [],
            "error_summary": run.error_summary,
            "model_metadata": run.model_metadata,
            "cost_summary": run.cost_summary,
        }
    )
    return detail


def list_runs(
    session: Session,
    *,
    page: int = 1,
    page_size: int = 25,
    application_id: str | None = None,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    """Paginated run list with filters (FR-F2)."""
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    stmt = select(EvaluationRun).order_by(EvaluationRun.created_at.desc())
    if application_id:
        stmt = stmt.where(
            EvaluationRun.application_id == _uuid(application_id, "application_id")
        )
    if status:
        try:
            status_value = RunStatus(status)
        except ValueError as exc:
            raise RunConfigError(f"unknown run status '{status}'") from exc
        stmt = stmt.where(EvaluationRun.status == status_value)
    if date_from:
        stmt = stmt.where(EvaluationRun.created_at >= date_from)
    if date_to:
        stmt = stmt.where(EvaluationRun.created_at < date_to)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = session.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [to_summary(r) for r in items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def _metric_row_to_dict(m: MetricResult) -> dict[str, Any]:
    return {
        "evaluator_id": m.evaluator_id,
        "evaluator_version": m.evaluator_version,
        "provenance": m.provenance.value if hasattr(m.provenance, "value") else str(m.provenance),
        "value_kind": m.value_kind.value if hasattr(m.value_kind, "value") else str(m.value_kind),
        "status": m.status.value if hasattr(m.status, "value") else str(m.status),
        "score": float(m.score) if m.score is not None else None,
        "unavailable_reason": m.unavailable_reason,
        "explanation": m.explanation,
        "details": m.details or {},
    }


def list_results(
    session: Session,
    run_id: str,
    *,
    page: int = 1,
    page_size: int = 25,
    outcome: str | None = None,
    evaluator_id: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    """Paginated per-case results for a run (FR-F1, contract CaseResult)."""
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    run = get_run_or_404(session, run_id)
    stmt = (
        select(TestResult, TestCase)
        .join(TestCase, TestResult.test_case_id == TestCase.id)
        .where(TestResult.evaluation_run_id == run.id)
        .order_by(TestCase.position, TestResult.repeat_index)
    )
    if outcome:
        try:
            outcome_value = CaseOutcome(outcome)
        except ValueError as exc:
            raise RunConfigError(f"unknown outcome '{outcome}'") from exc
        stmt = stmt.where(TestResult.outcome == outcome_value)
    if evaluator_id:
        stmt = stmt.where(
            TestResult.metric_results.any(MetricResult.evaluator_id == evaluator_id)
        )
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            (TestCase.external_id.ilike(pattern)) | (TestCase.category.ilike(pattern))
        )
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    items = [_result_item(result, case) for result, case in rows]
    return {"items": items, "page": page, "page_size": page_size, "total": total}


def _result_item(result: TestResult, case: TestCase | None) -> dict[str, Any]:
    metrics = sorted(result.metric_results, key=lambda m: m.evaluator_id)
    return {
        "id": str(result.id),
        "run_id": str(result.evaluation_run_id),
        "test_case_id": str(result.test_case_id),
        "external_id": case.external_id if case else None,
        "repeat_index": result.repeat_index,
        "outcome": result.outcome.value
        if hasattr(result.outcome, "value")
        else str(result.outcome),
        "actual_output": result.actual_output,
        "latency_ms": result.latency_ms,
        "ttft_ms": result.ttft_ms,
        "token_usage": result.token_usage,
        "error_type": result.error_type,
        "error_message": result.error_message,
        "metrics": [_metric_row_to_dict(m) for m in metrics],
    }


def get_result_detail(session: Session, run_id: str, result_id: str) -> dict[str, Any]:
    """Full trace for one case result (contract CaseResultDetail)."""
    run = get_run_or_404(session, run_id)
    result = session.get(TestResult, _uuid(result_id, "result_id"))
    if result is None or result.evaluation_run_id != run.id:
        raise HTTPException(status_code=404, detail="Result not found for this run")
    case = session.get(TestCase, result.test_case_id)
    detail = _result_item(result, case)
    docs = result.retrieved_documents or []
    doc_ids: list[str] = []
    for doc in docs:
        if isinstance(doc, dict):
            doc_id = doc.get("doc_id") or doc.get("id")
            if doc_id:
                doc_ids.append(str(doc_id))
        elif isinstance(doc, str) and doc:
            doc_ids.append(doc)
    detail.update(
        {
            "case_input": (case.input if case else {}) or {},
            "expected_output": case.expected_output if case else None,
            "retrieved_document_ids": doc_ids or None,
            "agent_trace": result.agent_trace,
            "category": case.category if case else None,
        }
    )
    return detail


def cancel_run(session: Session, run_id: str) -> EvaluationRun:
    """Cooperative cancellation (FR-C5, contract POST /evaluations/{id}/cancel)."""
    run = get_run_or_404(session, run_id)
    if run.status == RunStatus.QUEUED:
        run.status = RunStatus.CANCELLED
        run.completed_at = _now()
        session.add(
            RunEvent(
                evaluation_run_id=run.id,
                event_type=RunEventType.CANCELLED,
                payload={"reason": "cancelled while queued"},
            )
        )
        session.commit()
        session.refresh(run)
        return run
    if run.status == RunStatus.RUNNING:
        error_summary = dict(run.error_summary or {})
        error_summary["cancel_requested"] = True
        run.error_summary = error_summary  # reassign so the JSON change persists
        session.add(
            RunEvent(
                evaluation_run_id=run.id,
                event_type=RunEventType.WARNING,
                payload={"message": "cancellation requested"},
            )
        )
        session.commit()
        session.refresh(run)
        return run
    raise InvalidRunStateError(f"run is already {run.status.value}")


def claim_next_queued_run(session: Session) -> str | None:
    """Atomically claim the oldest queued run; returns its id or None (T3.4)."""
    run = session.scalars(
        select(EvaluationRun)
        .where(EvaluationRun.status == RunStatus.QUEUED)
        .order_by(EvaluationRun.created_at)
        .limit(1)
    ).first()
    if run is None:
        return None
    result = session.execute(
        update(EvaluationRun)
        .where(EvaluationRun.id == run.id, EvaluationRun.status == RunStatus.QUEUED)
        .values(status=RunStatus.RUNNING, started_at=_now())
    )
    session.commit()
    if result.rowcount == 0:
        return None
    return str(run.id)


def execute_run(run_id: str) -> None:
    """Execute one run synchronously (worker thread or tests)."""
    engine = EvaluationEngine(DbEnginePorts())
    engine.run(run_id)


class DbEnginePorts:
    """EnginePorts implementation backed by the process session factory.

    Each method opens its own short-lived session so the background worker
    thread never shares a session with the API (and progress commits are
    visible immediately to polling clients).
    """

    def __init__(self) -> None:
        from app.db.session import get_session_factory

        self._factory = get_session_factory()

    def _session(self) -> Session:
        return self._factory()

    def load_plan(self, run_id: str) -> RunPlan:
        with self._session() as session:
            run = session.get(EvaluationRun, _uuid(run_id, "run_id"))
            if run is None:
                raise RunConfigError(f"run '{run_id}' not found")
            app = session.get(Application, run.application_id)
            cases = session.scalars(
                select(TestCase)
                .where(
                    TestCase.dataset_version_id == run.dataset_version_id,
                    TestCase.status == CaseStatus.VALID,
                )
                .order_by(TestCase.position)
            ).all()
            case_data = [
                CaseData(
                    id=str(c.id),
                    position=c.position,
                    case_input=dict(c.input or {"input": ""}),
                    expected_output=c.expected_output,
                    reference_context=c.reference_context,
                    relevant_doc_ids=c.relevant_doc_ids,
                    expected_tool=c.expected_tool,
                    expected_action_sequence=(
                        [str(a) for a in c.expected_action_sequence]
                        if c.expected_action_sequence is not None
                        else None
                    ),
                    category=c.category,
                    external_id=c.external_id,
                    is_security_case=c.is_security_case,
                )
                for c in cases
            ]
            model_name = None
            if run.application_config_id:
                config_row = session.get(ApplicationConfig, run.application_config_id)
                model_name = config_row.model_name if config_row else None
            return RunPlan(
                run_id=str(run.id),
                application_type=app.application_type.value,
                capabilities=capabilities_of(app),
                cases=case_data,
                selected_metrics=list(run.selected_metrics or []),
                run_config=dict(run.run_config or {}),
                model_name=model_name,
            )

    def build_adapter(self, run_id: str):
        with self._session() as session:
            run = session.get(EvaluationRun, _uuid(run_id, "run_id"))
            if run is None:
                raise RunConfigError(f"run '{run_id}' not found")
            app = session.get(Application, run.application_id)
            config = build_adapter_config(app)
            return get_adapter(app.integration_type.value, config)

    def is_cancel_requested(self, run_id: str) -> bool:
        with self._session() as session:
            run = session.get(EvaluationRun, _uuid(run_id, "run_id"))
            if run is None or run.status == RunStatus.CANCELLED:
                return True
            return bool((run.error_summary or {}).get("cancel_requested"))

    def mark_running(self, run_id: str) -> None:
        with self._session() as session:
            run = session.get(EvaluationRun, _uuid(run_id, "run_id"))
            if run is None:
                return
            if run.started_at is None:
                run.started_at = _now()
            session.add(
                RunEvent(
                    evaluation_run_id=run.id,
                    event_type=RunEventType.STARTED,
                    payload={},
                )
            )
            session.commit()

    def record_case(
        self, run_id: str, case_input: CaseEvalInput, metrics: list[MetricValue]
    ) -> None:
        """Persist TestResults (+ MetricResults on repeat 0) and progress."""
        with self._session() as session:
            run = session.get(EvaluationRun, _uuid(run_id, "run_id"))
            if run is None:
                return
            for repeat in case_input.repeats:
                test_result = TestResult(
                    evaluation_run_id=run.id,
                    test_case_id=_uuid(case_input.case.id, "test_case_id"),
                    repeat_index=repeat.repeat_index,
                    outcome=repeat.outcome,
                    actual_output=repeat.output,
                    retrieved_documents=(
                        [{"doc_id": d} for d in repeat.retrieved_document_ids]
                        if repeat.retrieved_document_ids is not None
                        else None
                    ),
                    citations=None,
                    agent_trace=repeat.agent_trace,
                    token_usage=repeat.token_usage,
                    ttft_ms=repeat.ttft_ms,
                    latency_ms=repeat.latency_ms,
                    error_type=repeat.error_type,
                    error_message=repeat.error_message,
                    started_at=_now(),
                )
                session.add(test_result)
                session.flush()
                if repeat.repeat_index == 0:
                    # Case metrics are computed over all repeats; attach to the
                    # first repeat's row only to avoid duplication.
                    for value in metrics:
                        session.add(
                            MetricResult(
                                test_result_id=test_result.id,
                                evaluator_id=value.evaluator_id,
                                evaluator_version=value.evaluator_version,
                                score=value.score,
                                value_kind=value.value_kind,
                                status=value.status,
                                unavailable_reason=value.unavailable_reason,
                                provenance=value.provenance,
                                explanation=value.explanation,
                                details=value.details,
                            )
                        )
            progress = dict(run.progress or {})
            for repeat in case_input.repeats:
                if repeat.outcome == CaseOutcome.SUCCESS:
                    progress["completed"] = progress.get("completed", 0) + 1
                elif repeat.outcome in (
                    CaseOutcome.APPLICATION_ERROR,
                    CaseOutcome.TIMEOUT,
                    CaseOutcome.INVALID_CASE,
                ):
                    progress["failed"] = progress.get("failed", 0) + 1
                else:
                    progress["skipped"] = progress.get("skipped", 0) + 1
            run.progress = progress  # reassign so the JSON change persists
            session.add(
                RunEvent(
                    evaluation_run_id=run.id,
                    event_type=RunEventType.CASE_COMPLETED,
                    payload={
                        "case_id": case_input.case.id,
                        "position": case_input.case.position,
                        "outcome": case_input.repeats[0].outcome.value
                        if case_input.repeats
                        else None,
                        "metrics": [m.to_dict() for m in metrics],
                    },
                )
            )
            session.commit()

    def finish(
        self,
            run_id: str,
            *,
            status: RunStatus,
            summary_metrics: list[MetricValue],
            error_summary: dict[str, Any] | None,
            model_metadata: dict[str, Any],
            duration_ms: int,
    ) -> None:
            """Persist terminal state: aggregates, cost summary, events."""
            from app.evaluation.pricing import PRICING_VERSION
            from app.models.enums import MetricStatus

            with self._session() as session:
                run = session.get(EvaluationRun, _uuid(run_id, "run_id"))
                if run is None:
                    return
                run.status = status
                run.completed_at = _now()
                run.duration_ms = duration_ms
                run.summary_metrics = [m.to_dict() for m in summary_metrics]
                run.error_summary = error_summary
                run.model_metadata = model_metadata
                cost_total = next(
                    (m for m in summary_metrics if m.evaluator_id == "cost.estimated_total"),
                    None,
                )
                if cost_total is not None and cost_total.status == MetricStatus.COMPUTED:
                    per_case = next(
                        (m for m in summary_metrics if m.evaluator_id == "cost.estimated_per_case"),
                        None,
                    )
                    run.cost_summary = {
                        "currency": "USD",
                        "pricing_version": cost_total.details.get(
                            "pricing_version", PRICING_VERSION
                        ),
                        "total_usd": cost_total.score,
                        "per_case_usd": per_case.score if per_case else None,
                    }
                event_type = {
                    RunStatus.COMPLETED: RunEventType.COMPLETED,
                    RunStatus.FAILED: RunEventType.FAILED,
                    RunStatus.CANCELLED: RunEventType.CANCELLED,
                }.get(status, RunEventType.WARNING)
                session.add(
                    RunEvent(
                        evaluation_run_id=run.id,
                        event_type=event_type,
                        payload={"status": status.value, "duration_ms": duration_ms},
                    )
                )
                session.commit()
