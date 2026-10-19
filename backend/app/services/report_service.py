"""Reporting services: run comparison (FR-F3), export (FR-H), overview (FR-G1).

Comparison regresses on stored aggregates and per-case outcomes only —
nothing is recomputed or fabricated. Unavailable metrics surface their
reason instead of a guessed delta (constitution §2.2/D4).
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.evaluation import registry
from app.evaluation.errors import ApplicabilityError, InvalidRunStateError
from app.models.application import Application
from app.models.dataset import Dataset, DatasetVersion, TestCase
from app.models.enums import CaseOutcome, MetricStatus, RunStatus
from app.models.evaluation import EvaluationRun
from app.models.results import MetricResult, TestResult
from app.services import run_service

# Value kinds where a lower score is better; all others regress when lower.
_LOWER_IS_BETTER = {"ms", "tokens", "currency", "count"}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _load_completed_run(session: Session, run_id: str, label: str) -> EvaluationRun:
    run = run_service.get_run_or_404(session, run_id)
    if run.status != RunStatus.COMPLETED:
        raise InvalidRunStateError(
            f"{label} run '{run_id}' is not completed (status: {run.status.value})"
        )
    return run


def _summary_map(run: EvaluationRun) -> dict[str, dict[str, Any]]:
    return {m.get("evaluator_id"): m for m in (run.summary_metrics or [])}


def _case_outcomes(session: Session, run: EvaluationRun) -> dict[str, str]:
    """Per-case outcome map keyed for cross-run matching (external_id first).

    A case counts as successful when any of its repeats succeeded; otherwise
    the first non-success outcome is kept.
    """
    rows = session.execute(
        select(TestResult, TestCase)
        .join(TestCase, TestResult.test_case_id == TestCase.id)
        .where(TestResult.evaluation_run_id == run.id)
        .order_by(TestCase.position, TestResult.repeat_index)
    ).all()
    outcomes: dict[str, str] = {}
    for result, case in rows:
        key = case.external_id or str(case.id)
        outcome = (
            result.outcome.value if hasattr(result.outcome, "value") else str(result.outcome)
        )
        if key not in outcomes or outcome == CaseOutcome.SUCCESS.value:
            outcomes[key] = outcome
    return outcomes


def _run_brief(session: Session, run: EvaluationRun) -> dict[str, Any]:
    app = session.get(Application, run.application_id)
    dataset = session.get(Dataset, run.dataset_id)
    version = session.get(DatasetVersion, run.dataset_version_id)
    return {
        "run_id": str(run.id),
        "application_id": str(run.application_id),
        "application_name": app.name if app else None,
        "dataset_name": dataset.name if dataset else None,
        "dataset_version_number": version.version_number if version else None,
        "dataset_version_id": str(run.dataset_version_id),
        "status": run.status.value if hasattr(run.status, "value") else str(run.status),
        "created_at": run_service._iso(run.created_at),
        "completed_at": run_service._iso(run.completed_at),
        "duration_ms": run.duration_ms,
    }


def compare_runs(
    session: Session, baseline_run_id: str, candidate_run_id: str
) -> dict[str, Any]:
    """Metric deltas, regressions, newly failing / resolved cases (FR-F3)."""
    if baseline_run_id == candidate_run_id:
        raise InvalidRunStateError("baseline and candidate runs must be different")
    baseline = _load_completed_run(session, baseline_run_id, "baseline")
    candidate = _load_completed_run(session, candidate_run_id, "candidate")

    base_snapshot = baseline.configuration_snapshot or {}
    cand_snapshot = candidate.configuration_snapshot or {}
    dataset_compatible = (
        base_snapshot.get("dataset", {}).get("id") == cand_snapshot.get("dataset", {}).get("id")
        and base_snapshot.get("dataset", {}).get("content_hash")
        == cand_snapshot.get("dataset", {}).get("content_hash")
    )

    base_outcomes = _case_outcomes(session, baseline)
    cand_outcomes = _case_outcomes(session, candidate)
    matched = [k for k in base_outcomes if k in cand_outcomes]
    if not matched:
        raise ApplicabilityError(
            "the two runs have no comparable cases (no overlapping case ids)"
        )
    success = CaseOutcome.SUCCESS.value
    newly_failing = [
        k for k in matched if base_outcomes[k] == success and cand_outcomes[k] != success
    ]
    resolved = [
        k for k in matched if base_outcomes[k] != success and cand_outcomes[k] == success
    ]

    base_metrics = _summary_map(baseline)
    cand_metrics = _summary_map(candidate)

    # Case-scope metrics are not in summary_metrics; aggregate them over the
    # matched cases from stored per-case MetricResults.
    base_case = _case_metric_scores(session, baseline, set(matched))
    cand_case = _case_metric_scores(session, candidate, set(matched))
    case_ids = sorted(set(base_case) & set(cand_case))

    deltas: dict[str, dict[str, Any]] = {}
    for evaluator_id in sorted(set(base_metrics) & set(cand_metrics)):
        deltas[evaluator_id] = _delta_entry(
            base_metrics[evaluator_id], cand_metrics[evaluator_id]
        )
    for evaluator_id in case_ids:
        base_value = _mean(base_case[evaluator_id])
        cand_value = _mean(cand_case[evaluator_id])
        if base_value is None or cand_value is None:
            continue
        if evaluator_id in deltas:
            continue  # run-scope aggregate takes precedence
        # value_kind comes from the registry (single source of truth).
        try:
            registry.ensure_loaded()
            spec, _ = registry.get(evaluator_id)
            kind = spec.value_kind.value
        except Exception:
            kind = "score"
        delta = round(cand_value - base_value, 6)
        deltas[evaluator_id] = {
            "evaluator_id": evaluator_id,
            "baseline": base_value,
            "candidate": cand_value,
            "delta": delta,
            "regression": (delta > 0 if kind in _LOWER_IS_BETTER else delta < 0),
            "provenance": "measured",
            "value_kind": kind,
            "unavailable_reason": None,
        }
    metric_deltas = [deltas[k] for k in sorted(deltas)]

    latency_delta = None
    cost_delta = None
    if "performance.latency" in base_metrics and "performance.latency" in cand_metrics:
        latency_delta = _latency_delta(
            base_metrics["performance.latency"], cand_metrics["performance.latency"]
        )
    if "cost.estimated_total" in base_metrics and "cost.estimated_total" in cand_metrics:
        cost_delta = {
            "baseline_total_usd": base_metrics["cost.estimated_total"].get("score"),
            "candidate_total_usd": cand_metrics["cost.estimated_total"].get("score"),
            "delta_usd": _diff(
                base_metrics["cost.estimated_total"].get("score"),
                cand_metrics["cost.estimated_total"].get("score"),
            ),
            "unavailable_reason": deltas.get("cost.estimated_total", {}).get(
                "unavailable_reason"
            ),
        }
    elif "cost.estimated_total" in base_metrics or "cost.estimated_total" in cand_metrics:
        cost_delta = {"unavailable_reason": "cost not measured in both runs"}
    return {
        "baseline_run_id": str(baseline.id),
        "candidate_run_id": str(candidate.id),
        "dataset_compatible": dataset_compatible,
        "metric_deltas": metric_deltas,
        "newly_failing_case_ids": newly_failing,
        "resolved_case_ids": resolved,
        "latency_delta": latency_delta,
        "cost_delta": cost_delta,
        "baseline": _run_brief(session, baseline),
        "candidate": _run_brief(session, candidate),
    }


def _diff(base: Any, cand: Any) -> float | None:
    if base is None or cand is None:
        return None
    return round(float(cand) - float(base), 6)


def _latency_delta(base_metric: dict[str, Any], cand_metric: dict[str, Any]) -> dict[str, Any]:
    return {
        "baseline_mean_ms": base_metric.get("score"),
        "candidate_mean_ms": cand_metric.get("score"),
        "delta_ms": _diff(base_metric.get("score"), cand_metric.get("score")),
        "baseline_p95_ms": (base_metric.get("details") or {}).get("p95"),
        "candidate_p95_ms": (cand_metric.get("details") or {}).get("p95"),
    }


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _delta_entry(base_metric: dict[str, Any], cand_metric: dict[str, Any]) -> dict[str, Any]:
    """Delta entry for a run-scope (aggregate) metric present in both runs."""
    entry: dict[str, Any] = {
        "evaluator_id": base_metric.get("evaluator_id"),
        "baseline": None,
        "candidate": None,
        "delta": None,
        "regression": None,
        "provenance": base_metric.get("provenance", "measured"),
        "value_kind": base_metric.get("value_kind", "score"),
        "unavailable_reason": None,
    }
    reasons = [
        m.get("unavailable_reason")
        for m in (base_metric, cand_metric)
        if m.get("status") != MetricStatus.COMPUTED.value
    ]
    if reasons:
        entry["unavailable_reason"] = "; ".join(r for r in reasons if r)
        return entry
    base_score = float(base_metric.get("score") or 0.0)
    cand_score = float(cand_metric.get("score") or 0.0)
    delta = round(cand_score - base_score, 6)
    entry["baseline"] = base_score
    entry["candidate"] = cand_score
    entry["delta"] = delta
    if entry["value_kind"] in _LOWER_IS_BETTER:
        entry["regression"] = delta > 0
    else:
        entry["regression"] = delta < 0
    return entry


def _case_metric_scores(
    session: Session, run: EvaluationRun, keys: set[str]
) -> dict[str, list[float]]:
    """Scores per case-scope evaluator over the matched cases of one run."""
    rows = session.execute(
        select(MetricResult, TestCase)
        .join(TestResult, MetricResult.test_result_id == TestResult.id)
        .join(TestCase, TestResult.test_case_id == TestCase.id)
        .where(TestResult.evaluation_run_id == run.id)
    ).all()
    scores: dict[str, list[float]] = {}
    for metric, case in rows:
        key = case.external_id or str(case.id)
        if key not in keys:
            continue
        if metric.status == MetricStatus.COMPUTED and metric.score is not None:
            scores.setdefault(metric.evaluator_id, []).append(float(metric.score))
    return scores


def _run_cases(session: Session, run: EvaluationRun) -> list[dict[str, Any]]:
    """All per-case records for export (every repeat, sanitized fields only)."""
    rows = session.execute(
        select(TestResult, TestCase)
        .join(TestCase, TestResult.test_case_id == TestCase.id)
        .where(TestResult.evaluation_run_id == run.id)
        .order_by(TestCase.position, TestResult.repeat_index)
    ).all()
    items: list[dict[str, Any]] = []
    for result, case in rows:
        usage = result.token_usage or {}
        items.append(
            {
                "case_id": str(case.id),
                "external_id": case.external_id,
                "category": case.category,
                "repeat_index": result.repeat_index,
                "outcome": result.outcome.value
                if hasattr(result.outcome, "value")
                else str(result.outcome),
                "case_input": (case.input or {}).get("input"),
                "expected_output": case.expected_output,
                "actual_output": result.actual_output,
                "latency_ms": result.latency_ms,
                "ttft_ms": result.ttft_ms,
                "input_tokens": usage.get("input"),
                "output_tokens": usage.get("output"),
                "error_type": result.error_type,
                "error_message": result.error_message,
                "metrics": [
                    {
                        "evaluator_id": m.evaluator_id,
                        "evaluator_version": m.evaluator_version,
                        "status": m.status.value if hasattr(m.status, "value") else str(m.status),
                        "provenance": m.provenance.value
                        if hasattr(m.provenance, "value")
                        else str(m.provenance),
                        "score": float(m.score) if m.score is not None else None,
                        "unavailable_reason": m.unavailable_reason,
                        "explanation": m.explanation,
                    }
                    for m in sorted(result.metric_results, key=lambda x: x.evaluator_id)
                ],
            }
        )
    return items


def build_export_payload(session: Session, run: EvaluationRun) -> dict[str, Any]:
    """Full structured run report (FR-H1/H3)."""
    registry.ensure_loaded()
    snapshot = run.configuration_snapshot or {}
    definitions = []
    for entry in run.selected_metrics or []:
        evaluator_id = entry.get("evaluator_id", entry) if isinstance(entry, dict) else entry
        try:
            spec, _ = registry.get(evaluator_id)
        except Exception:
            spec = None
        if spec is not None:
            definitions.append(
                {
                    "id": spec.id,
                    "name": spec.name,
                    "description": spec.description,
                    "version": spec.version,
                    "provenance": spec.provenance.value,
                    "value_kind": spec.value_kind.value,
                    "scope": spec.scope,
                }
            )
    cases = _run_cases(session, run)
    return {
        "report_version": "1.0.0",
        "generated_at": _now_iso(),
        "run": {
            "id": str(run.id),
            "status": run.status.value if hasattr(run.status, "value") else str(run.status),
            "progress": run.progress or {},
            "run_config": run.run_config or {},
            "triggered_by": run.triggered_by,
            "created_at": run_service._iso(run.created_at),
            "started_at": run_service._iso(run.started_at),
            "completed_at": run_service._iso(run.completed_at),
            "duration_ms": run.duration_ms,
        },
        "application": snapshot.get("application"),
        "dataset": snapshot.get("dataset"),
        "metric_definitions": definitions,
        "summary_metrics": run.summary_metrics or [],
        "cases": cases,
        "failed_cases": [c for c in cases if c["outcome"] != CaseOutcome.SUCCESS.value],
        "error_summary": run.error_summary,
        "cost_summary": run.cost_summary,
        "model_metadata": run.model_metadata,
    }


def export_csv(session: Session, run: EvaluationRun) -> str:
    """CSV export (FR-H2): one row per case repeat + aggregate section."""
    payload = build_export_payload(session, run)
    metric_ids = sorted({m["evaluator_id"] for c in payload["cases"] for m in c["metrics"]})
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "case_id", "external_id", "category", "repeat_index", "outcome",
            "case_input", "expected_output", "actual_output", "latency_ms", "ttft_ms",
            "input_tokens", "output_tokens", "error_type", "error_message", *metric_ids,
        ]
    )
    for case in payload["cases"]:
        scores = {m["evaluator_id"]: m for m in case["metrics"]}
        writer.writerow(
            [
                case["case_id"], case["external_id"], case["category"],
                case["repeat_index"], case["outcome"], case["case_input"],
                case["expected_output"], case["actual_output"], case["latency_ms"],
                case["ttft_ms"], case["input_tokens"], case["output_tokens"],
                case["error_type"], case["error_message"],
                *[(scores[mid].get("score") if mid in scores else "") for mid in metric_ids],
            ]
        )
    writer.writerow([])
    writer.writerow(
        ["evaluator_id", "evaluator_version", "status", "provenance", "score", "unavailable_reason"]
    )
    for metric in payload["summary_metrics"]:
        writer.writerow(
            [
                metric.get("evaluator_id"), metric.get("evaluator_version"),
                metric.get("status"), metric.get("provenance"),
                metric.get("score"), metric.get("unavailable_reason"),
            ]
        )
    return buf.getvalue()


def overview(session: Session) -> dict[str, Any]:
    """Dashboard aggregates from real data only (FR-G1)."""
    runs_total = session.scalar(select(func.count()).select_from(EvaluationRun)) or 0
    apps_total = session.scalar(select(func.count()).select_from(Application)) or 0
    apps_enabled = (
        session.scalar(
            select(func.count()).select_from(Application).where(Application.is_enabled)
        )
        or 0
    )
    datasets_total = session.scalar(select(func.count()).select_from(Dataset)) or 0
    cases_executed = session.scalar(select(func.count()).select_from(TestResult)) or 0

    breakdown_rows = session.execute(
        select(EvaluationRun.status, func.count()).group_by(EvaluationRun.status)
    ).all()
    status_breakdown = [
        {"status": (s.value if hasattr(s, "value") else str(s)), "count": count}
        for s, count in breakdown_rows
    ]

    recent_runs = [
        run_service.to_summary(r)
        for r in session.scalars(
            select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(5)
        ).all()
    ]

    key_metrics: list[dict[str, Any]] = []
    completed = session.scalars(
        select(EvaluationRun)
        .where(EvaluationRun.status == RunStatus.COMPLETED)
        .order_by(EvaluationRun.completed_at.desc())
        .limit(5)
    ).all()
    for run in completed:
        summary = _summary_map(run)
        success = summary.get("reliability.success_rate") or {}
        latency = summary.get("performance.latency") or {}
        cost = summary.get("cost.estimated_total") or {}
        app = session.get(Application, run.application_id)
        key_metrics.append(
            {
                "run_id": str(run.id),
                "application_name": app.name if app else None,
                "completed_at": run_service._iso(run.completed_at),
                "success_rate": success.get("score"),
                "success_rate_status": success.get("status", "unavailable"),
                "latency_mean_ms": latency.get("score"),
                "latency_status": latency.get("status", "unavailable"),
                "total_cost_usd": cost.get("score"),
                "cost_status": cost.get("status", "unavailable"),
            }
        )

    failures = session.execute(
        select(TestResult, TestCase, EvaluationRun)
        .join(TestCase, TestResult.test_case_id == TestCase.id)
        .join(EvaluationRun, TestResult.evaluation_run_id == EvaluationRun.id)
        .where(TestResult.outcome.in_([CaseOutcome.APPLICATION_ERROR, CaseOutcome.TIMEOUT]))
        .order_by(EvaluationRun.created_at.desc(), TestCase.position)
        .limit(5)
    ).all()
    recent_failures = [
        {
            "result_id": str(result.id),
            "run_id": str(run.id),
            "external_id": case.external_id,
            "outcome": result.outcome.value
            if hasattr(result.outcome, "value")
            else str(result.outcome),
            "error_type": result.error_type,
            "error_message": result.error_message,
            "created_at": run_service._iso(run.created_at),
        }
        for result, case, run in failures
    ]

    return {
        "totals": {
            "applications": apps_total,
            "applications_enabled": apps_enabled,
            "datasets": datasets_total,
            "runs": runs_total,
            "cases_executed": cases_executed,
        },
        "status_breakdown": status_breakdown,
        "recent_runs": recent_runs,
        "key_metrics": key_metrics,
        "recent_failures": recent_failures,
    }



