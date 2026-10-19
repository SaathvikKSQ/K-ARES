"""Evaluation endpoints (FR-C, FR-E, FR-F1/F2; contract Evaluations section).

All routes require authentication; mutations (create/cancel) require
editor/admin role. Note: ``/evaluations/validate-config`` is declared before
``/evaluations/{run_id}`` so it is not captured as a run id.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import CurrentUser, DbSession, EditorUser
from app.evaluation import registry
from app.evaluation.errors import (
    ApplicabilityError,
    EvaluationError,
    InvalidRunStateError,
    RunConfigError,
    UnknownEvaluatorError,
)
from app.schemas.report import CompareOut, CompareRequest
from app.schemas.run import (
    CaseResultDetailOut,
    PageOut,
    RunCreate,
    RunDetailOut,
    RunSummaryOut,
    ValidateConfigIn,
    ValidateConfigOut,
)
from app.services import report_service
from app.services import run_service as svc

router = APIRouter(tags=["evaluations"])

_ERROR_STATUS: list[tuple[type[EvaluationError], int]] = [
    (UnknownEvaluatorError, status.HTTP_400_BAD_REQUEST),
    (RunConfigError, status.HTTP_400_BAD_REQUEST),
    (ApplicabilityError, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (InvalidRunStateError, status.HTTP_409_CONFLICT),
]


def _map_error(exc: EvaluationError) -> HTTPException:
    """Translate engine errors into the standard envelope (code + message)."""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    for error_type, code in _ERROR_STATUS:
        if isinstance(exc, error_type):
            status_code = code
            break
    message = exc.message
    if exc.details:
        joined = "; ".join(str(d.get("message", "")) for d in exc.details)
        message = f"{message} ({joined})"
    return HTTPException(status_code=status_code, detail=message)


def _parse_dt(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} must be an ISO-8601 timestamp",
        ) from exc


@router.get("/metrics", response_model=list[dict])
def list_metrics(session: DbSession, user: CurrentUser):
    """Registered evaluator specs (registry-driven, FR-E1)."""
    registry.ensure_loaded()
    return [
        {
            "id": spec.id,
            "name": spec.name,
            "description": spec.description,
            "version": spec.version,
            "provenance": spec.provenance.value,
            "value_kind": spec.value_kind.value,
            "scope": spec.scope,
            "application_types": list(spec.application_types),
            "required_fields": list(spec.required_fields),
            "capabilities_required": list(spec.capabilities_required),
            "config_schema": spec.config_schema,
        }
        for spec in registry.list_specs()
    ]


@router.post("/evaluations/validate-config", response_model=ValidateConfigOut)
def validate_config(payload: ValidateConfigIn, session: DbSession, user: EditorUser):
    """Applicability preview without queueing (dry-run, FR-C2)."""
    try:
        return svc.validate_config(session, payload)
    except EvaluationError as exc:
        raise _map_error(exc) from exc


@router.post(
    "/evaluations", response_model=RunSummaryOut, status_code=status.HTTP_202_ACCEPTED
)
def create_evaluation(payload: RunCreate, session: DbSession, user: EditorUser):
    """Queue an evaluation run (async start; FR-C1)."""
    try:
        run = svc.create_run(session, payload, user.email)
    except EvaluationError as exc:
        raise _map_error(exc) from exc
    return svc.to_summary(run)


@router.get("/evaluations", response_model=PageOut)
def list_evaluations(
    session: DbSession,
    user: CurrentUser,
    page: int = 1,
    page_size: int = 25,
    application_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Run history with filters (FR-F2)."""
    try:
        return svc.list_runs(
            session,
            page=page,
            page_size=page_size,
            application_id=application_id,
            status=status_filter,
            date_from=_parse_dt(date_from, "date_from") if date_from else None,
            date_to=_parse_dt(date_to, "date_to") if date_to else None,
        )
    except EvaluationError as exc:
        raise _map_error(exc) from exc


@router.get("/evaluations/{run_id}", response_model=RunDetailOut)
def get_evaluation(run_id: str, session: DbSession, user: CurrentUser):
    """Run detail: status, progress, aggregates with provenance (FR-F1)."""
    return svc.to_detail(svc.get_run_or_404(session, run_id))


@router.get("/evaluations/{run_id}/results", response_model=PageOut)
def list_run_results(
    run_id: str,
    session: DbSession,
    user: CurrentUser,
    page: int = 1,
    page_size: int = 25,
    outcome: str | None = None,
    evaluator_id: str | None = None,
    search: str | None = None,
):
    """Per-case results (inputs/outputs/scores/errors; FR-F1)."""
    try:
        return svc.list_results(
            session,
            run_id,
            page=page,
            page_size=page_size,
            outcome=outcome,
            evaluator_id=evaluator_id,
            search=search,
        )
    except EvaluationError as exc:
        raise _map_error(exc) from exc


@router.get(
    "/evaluations/{run_id}/results/{result_id}", response_model=CaseResultDetailOut
)
def get_run_result(run_id: str, result_id: str, session: DbSession, user: CurrentUser):
    """Full trace and explanations for one case result."""
    try:
        return svc.get_result_detail(session, run_id, result_id)
    except EvaluationError as exc:
        raise _map_error(exc) from exc


@router.post(
    "/evaluations/{run_id}/cancel",
    response_model=RunSummaryOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def cancel_evaluation(run_id: str, session: DbSession, user: EditorUser):
    """Cooperative cancellation (FR-C5)."""
    try:
        run = svc.cancel_run(session, run_id)
    except EvaluationError as exc:
        raise _map_error(exc) from exc
    return svc.to_summary(run)

    return svc.to_summary(run)


@router.post("/evaluations/compare", response_model=CompareOut)
def compare_evaluations(payload: CompareRequest, session: DbSession, user: CurrentUser):
    """Compare two completed runs: deltas, regressions, case flips (FR-F3)."""
    try:
        return report_service.compare_runs(
            session, payload.baseline_run_id, payload.candidate_run_id
        )
    except EvaluationError as exc:
        raise _map_error(exc) from exc


@router.get("/evaluations/{run_id}/export")
def export_evaluation(
    run_id: str,
    session: DbSession,
    user: CurrentUser,
    format: str = Query(default="json", pattern="^(json|csv)$"),
):
    """Download a run report as JSON or CSV (FR-H1/H2/H3)."""
    run = svc.get_run_or_404(session, run_id)
    safe_format = format.lower()
    if safe_format == "csv":
        content = report_service.export_csv(session, run)
        media_type = "text/csv; charset=utf-8"
        filename = f"run-{run_id}-export.csv"
    else:
        import json as _json

        content = _json.dumps(
            report_service.build_export_payload(session, run), indent=2, default=str
        )
        media_type = "application/json"
        filename = f"run-{run_id}-export.json"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
